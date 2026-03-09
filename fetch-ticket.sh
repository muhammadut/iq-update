#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Fetch a full Azure DevOps work item package (fields + comments + revisions + updates + attachments).

Usage:
  export ADO_PAT='...'
  export ADO_ORG='your-org'
  export ADO_PROJECT='Your Project Name'
  ./fetch-ticket.sh <work_item_id_or_url>

Options via env:
  ADO_OUT_DIR   Output directory (default: current directory)
  ADO_ID        Fallback work item id if argument is omitted

Output:
  workitem-<id>-full/
    raw/
      workitem.json
      comments.json
      updates.json
      revisions.json
      linked-workitems.json
      attachments.json
    attachments/
      <downloaded files>
    full-ticket.json
    llm-context.json
    llm-context.md
EOF
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

need_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "Missing required env var: $name" >&2
    exit 1
  fi
}

resolve_work_item_id() {
  local input="$1"
  if [[ "$input" =~ ^[0-9]+$ ]]; then
    printf '%s' "$input"
    return
  fi

  local parsed
  parsed="$(printf '%s' "$input" | sed -nE 's#.*(/_workitems/edit/|/workItems/)([0-9]+).*#\2#p')"
  if [ -n "$parsed" ]; then
    printf '%s' "$parsed"
    return
  fi

  echo "Could not extract a work item id from input: $input" >&2
  exit 1
}

sanitize_filename() {
  local value="$1"
  value="${value//\//_}"
  value="${value//\\/__}"
  value="${value//:/_}"
  value="${value//\?/_}"
  value="${value//\*/_}"
  value="${value//\"/_}"
  value="${value//</_}"
  value="${value//>/_}"
  value="${value//|/_}"
  value="$(printf '%s' "$value" | sed -E 's/[[:space:]]+/_/g')"
  if [ -z "$value" ]; then
    value="attachment"
  fi
  printf '%s' "$value"
}

urldecode() {
  local value="${1//+/ }"
  printf '%b' "${value//%/\\x}"
}

urlencode() {
  printf '%s' "$1" | jq -sRr @uri | tr -d '\r'
}

curl_json() {
  local url="$1"
  local out="$2"
  curl -fSs -u ":$ADO_PAT" "$url" -o "$out"
}

fetch_comments() {
  local out_file="$1"
  local token=""
  local page=1
  local page_arrays=()

  while true; do
    local url="${BASE_URL}/_apis/wit/workItems/${WORK_ITEM_ID}/comments?api-version=7.1-preview.4&%24top=200"
    if [ -n "$token" ]; then
      url="${url}&continuationToken=${token}"
    fi

    local page_json="${RAW_DIR}/comments-page-${page}.json"
    local page_array="${RAW_DIR}/comments-page-${page}-items.json"
    curl_json "$url" "$page_json"
    jq '.comments // []' "$page_json" >"$page_array"
    page_arrays+=("$page_array")

    token="$(jq -r '.continuationToken // empty' "$page_json" | tr -d '\r')"
    if [ -z "$token" ] || [ "$token" = "null" ]; then
      break
    fi
    page=$((page + 1))
  done

  jq -s '{count:(map(length) | add), comments:(add)}' "${page_arrays[@]}" >"$out_file"
}

fetch_skip_paged_collection() {
  local endpoint="$1"
  local out_file="$2"
  local top=200
  local skip=0
  local page=1
  local page_arrays=()

  while true; do
    local url="${BASE_URL}/_apis/wit/workItems/${WORK_ITEM_ID}/${endpoint}?api-version=7.1&%24top=${top}&%24skip=${skip}"
    local page_json="${RAW_DIR}/${endpoint}-page-${page}.json"
    local page_array="${RAW_DIR}/${endpoint}-page-${page}-items.json"
    local count

    curl_json "$url" "$page_json"
    jq '.value // []' "$page_json" >"$page_array"
    page_arrays+=("$page_array")
    count="$(jq -r '.count // 0' "$page_json" | tr -d '\r')"

    if [ "$count" -lt "$top" ]; then
      break
    fi
    skip=$((skip + top))
    page=$((page + 1))
  done

  jq -s --arg key "$endpoint" '{count:(map(length) | add), ($key):(add)}' "${page_arrays[@]}" >"$out_file"
}

fetch_linked_workitems() {
  local out_file="$1"
  local ids_file="${RAW_DIR}/linked-workitem-ids.txt"

  jq -r '
    .relations[]?
    | select(.url? and (.url | test("/_apis/wit/workItems/[0-9]+$")))
    | .url
    | capture("/_apis/wit/workItems/(?<id>[0-9]+)$")
    | .id
  ' "${RAW_DIR}/workitem.json" | tr -d '\r' | sort -n | uniq >"$ids_file"

  if [ ! -s "$ids_file" ]; then
    printf '[]\n' >"$out_file"
    return
  fi

  local jsonl="${RAW_DIR}/linked-workitems.jsonl"
  : >"$jsonl"

  while IFS= read -r linked_id; do
    local linked_json="${RAW_DIR}/linked-workitem-${linked_id}.json"
    local linked_url="${BASE_URL}/_apis/wit/workItems/${linked_id}?%24expand=All&api-version=7.1"
    curl_json "$linked_url" "$linked_json"
    cat "$linked_json" >>"$jsonl"
    printf '\n' >>"$jsonl"
  done <"$ids_file"

  jq -s '.' "$jsonl" >"$out_file"
}

build_attachment_manifest() {
  local relation_manifest="${RAW_DIR}/relation-attachments.tsv"
  local comment_manifest="${RAW_DIR}/comment-attachments.tsv"
  local description_manifest="${RAW_DIR}/description-attachments.tsv"
  local merged_manifest="$1"

  jq -r '
    .relations[]?
    | select(.rel == "AttachedFile")
    | . as $rel
    | ($rel.attributes.name // ("attachment-" + (($rel.attributes.id // "unknown") | tostring))) as $name
    | ($rel.url
      + (if ($rel.url | contains("?")) then "&" else "?" end)
      + "fileName="
      + ($name | @uri)
      + "&download=true") as $download_url
    | ["relation", $name, $download_url] | @tsv
  ' "${RAW_DIR}/workitem.json" | tr -d '\r' >"$relation_manifest"

  jq -r '
    .comments[]?.text // ""
    | gsub("&amp;"; "&")
    | scan("https://[^\"< ]+/_apis/wit/attachments/[^\"< ]+")
    | ["comment_image", "embedded-attachment", (if contains("download=true") then . else . + (if contains("?") then "&" else "?" end) + "download=true" end)]
    | @tsv
  ' "${RAW_DIR}/comments.json" | tr -d '\r' | sort -u >"$comment_manifest"

  # Fix 1: Extract images embedded in Description and ReproSteps HTML fields
  jq -r '
    def extract_image_urls(field_name; source_label):
      (.fields[field_name] // "")
      | gsub("&amp;"; "&") as $html
      | (
          [ $html | scan("https://[^\"< ]+/_apis/wit/attachments/[^\"< ]+") ]
          + [ $html | scan("src=\"(https://[^\"]+)\"") | .[0] ]
        )
      | map(select(. != null and length > 0 and test("https://")))
      | unique
      | .[]
      | [source_label, "embedded-attachment", (if contains("download=true") then . else . + (if contains("?") then "&" else "?" end) + "download=true" end)]
      | @tsv;

    (extract_image_urls("System.Description"; "description_image")),
    (extract_image_urls("Microsoft.VSTS.TCM.ReproSteps"; "repro_image"))
  ' "${RAW_DIR}/workitem.json" | tr -d '\r' | sort -u >"$description_manifest"

  # Merge all manifests with dedup by attachment GUID
  local all_manifests=()
  [ -s "$relation_manifest" ] && all_manifests+=("$relation_manifest")
  [ -s "$comment_manifest" ] && all_manifests+=("$comment_manifest")
  [ -s "$description_manifest" ] && all_manifests+=("$description_manifest")

  if [ ${#all_manifests[@]} -gt 0 ]; then
    cat "${all_manifests[@]}" \
      | awk -F'\t' '
          function attachment_key(url, key) {
            key = url
            sub(/^.*\/_apis\/wit\/attachments\//, "", key)
            sub(/\?.*$/, "", key)
            return tolower(key)
          }
          {
            key = attachment_key($3)
            if (!(key in seen)) {
              seen[key] = 1
              print
            }
          }
        ' >"$merged_manifest"
  else
    : >"$merged_manifest"
  fi
}

download_attachments() {
  local manifest="$1"
  local out_json="$2"
  local jsonl="${RAW_DIR}/attachments.jsonl"
  local index=0
  : >"$jsonl"

  if [ ! -s "$manifest" ]; then
    printf '[]\n' >"$out_json"
    return
  fi

  while IFS=$'\t' read -r source name url; do
    [ -z "${url:-}" ] && continue
    index=$((index + 1))

    local guessed_name
    guessed_name="$(printf '%s\n' "$url" | sed -n 's/.*[?&]fileName=\([^&]*\).*/\1/p')"
    local display_name="${name}"
    if [ -n "$guessed_name" ]; then
      display_name="$(urldecode "$guessed_name")"
    fi
    local local_name="${display_name}"
    local_name="$(sanitize_filename "$local_name")"
    local local_file="${index}-${local_name}"
    local local_path="${ATTACH_DIR}/${local_file}"

    # Fix 2: Extract attachment_id (GUID) from the URL path
    local attachment_id=""
    attachment_id="$(printf '%s\n' "$url" | sed -nE 's#.*/_apis/wit/attachments/([0-9a-fA-F-]+).*#\1#p')"

    # Fix 2: Map source to origin_kind
    local origin_kind="$source"

    if curl -fSs -u ":$ADO_PAT" "$url" -o "$local_path"; then
      local size
      size="$(wc -c <"$local_path" | tr -d ' ')"
      jq -n \
        --argjson index "$index" \
        --arg source "$source" \
        --arg origin_kind "$origin_kind" \
        --arg attachment_id "$attachment_id" \
        --arg name "$display_name" \
        --arg downloadUrl "$url" \
        --arg localPath "attachments/${local_file}" \
        --arg status "downloaded" \
        --argjson size "$size" \
        '{
          index: $index,
          source: $source,
          origin_kind: $origin_kind,
          attachment_id: $attachment_id,
          name: $name,
          downloadUrl: $downloadUrl,
          localPath: $localPath,
          status: $status,
          sizeBytes: $size
        }' >>"$jsonl"
    else
      rm -f "$local_path"
      jq -n \
        --argjson index "$index" \
        --arg source "$source" \
        --arg origin_kind "$origin_kind" \
        --arg attachment_id "$attachment_id" \
        --arg name "$display_name" \
        --arg downloadUrl "$url" \
        --arg localPath "" \
        --arg status "failed" \
        '{
          index: $index,
          source: $source,
          origin_kind: $origin_kind,
          attachment_id: $attachment_id,
          name: $name,
          downloadUrl: $downloadUrl,
          localPath: $localPath,
          status: $status
        }' >>"$jsonl"
    fi
    printf '\n' >>"$jsonl"
  done <"$manifest"

  jq -s '.' "$jsonl" >"$out_json"
}

build_llm_context() {
  local full_json="$1"
  local out_json="$2"
  local out_md="$3"

  jq '
    def html_to_md:
      (tostring // "")
      | gsub("\r"; "")
      | gsub("(?i)<br\\s*/?>"; "\n")
      | gsub("(?i)</p>"; "\n\n")
      | gsub("(?i)<p[^>]*>"; "")
      | gsub("(?i)</div>"; "\n")
      | gsub("(?i)<div[^>]*>"; "")
      | gsub("(?i)<li[^>]*>"; "- ")
      | gsub("(?i)</li>"; "\n")
      | gsub("(?i)<(ul|ol)[^>]*>"; "\n")
      | gsub("(?i)</(ul|ol)>"; "\n")
      | gsub("(?i)<h1[^>]*>"; "# ")
      | gsub("(?i)</h1>"; "\n\n")
      | gsub("(?i)<h2[^>]*>"; "## ")
      | gsub("(?i)</h2>"; "\n\n")
      | gsub("(?i)<h3[^>]*>"; "### ")
      | gsub("(?i)</h3>"; "\n\n")
      | gsub("(?i)<h4[^>]*>"; "#### ")
      | gsub("(?i)</h4>"; "\n\n")
      | gsub("(?i)<h5[^>]*>"; "##### ")
      | gsub("(?i)</h5>"; "\n\n")
      | gsub("(?i)<h6[^>]*>"; "###### ")
      | gsub("(?i)</h6>"; "\n\n")
      | gsub("(?i)<a[^>]*href=\"(?<u>[^\"]+)\"[^>]*>(?<t>.*?)</a>"; "[\(.t)](\(.u))")
      | gsub("(?i)<img[^>]*src=\"(?<src>[^\"]+)\"[^>]*>"; "![image](\(.src))")
      | gsub("(?i)<strong[^>]*>"; "**")
      | gsub("(?i)</strong>"; "**")
      | gsub("(?i)<b[^>]*>"; "**")
      | gsub("(?i)</b>"; "**")
      | gsub("(?i)<em[^>]*>"; "_")
      | gsub("(?i)</em>"; "_")
      | gsub("(?i)<i[^>]*>"; "_")
      | gsub("(?i)</i>"; "_")
      | gsub("(?i)<u[^>]*>"; "")
      | gsub("(?i)</u>"; "")
      | gsub("(?i)<table[^>]*>"; "\n")
      | gsub("(?i)</table>"; "\n")
      | gsub("(?i)<tr[^>]*>"; "\n| ")
      | gsub("(?i)</tr>"; " |")
      | gsub("(?i)<t[dh][^>]*>"; " | ")
      | gsub("(?i)</t[dh]>"; "")
      | gsub("(?i)</?thead[^>]*>"; "")
      | gsub("(?i)</?tbody[^>]*>"; "")
      | gsub("(?i)<[^>]+>"; "")
      | gsub("&nbsp;"; " ")
      | gsub("&amp;"; "&")
      | gsub("&lt;"; "<")
      | gsub("&gt;"; ">")
      | gsub("&quot;"; "\"")
      | gsub("&#39;"; "\u0027")
      | gsub("&#x27;"; "\u0027")
      | gsub("&#[0-9]+;"; "")
      | gsub("[ \t]+\n"; "\n")
      | gsub("\n[ \t]+"; "\n")
      | gsub("\n{3,}"; "\n\n")
      | gsub("^[ \t]+"; "")
      | gsub("[ \t]+$"; "");

    {
      metadata: .metadata,
      ticket: {
        id: .metadata.workItemId,
        title: (.workItem.fields["System.Title"] // ""),
        type: (.workItem.fields["System.WorkItemType"] // ""),
        state: (.workItem.fields["System.State"] // ""),
        tags: (
          (.workItem.fields["System.Tags"] // "")
          | split(";")
          | map(gsub("^\\s+|\\s+$"; ""))
          | map(select(length > 0))
        ),
        markdown: ((.workItem.fields["System.Description"] // "") | html_to_md),
        reproStepsMarkdown: ((.workItem.fields["Microsoft.VSTS.TCM.ReproSteps"] // "") | html_to_md)
      },
      comments: (
        [.comments.comments[]? | {
          id: .id,
          author: (.createdBy.displayName // .createdBy.uniqueName // "unknown"),
          createdDate: .createdDate,
          markdown: ((.text // "") | html_to_md)
        }]
      ),
      attachments: (
        [.attachments[]?
          | {
            index: .index,
            name: .name,
            source: .source,
            origin_kind: .origin_kind,
            attachment_id: .attachment_id,
            localPath: .localPath,
            status: .status,
            sizeBytes: .sizeBytes
          }
        ]
      )
    }
    | if (
        (.ticket.reproStepsMarkdown | length) == 0
        or (.ticket.reproStepsMarkdown == .ticket.markdown)
        or (.ticket.reproStepsMarkdown | test("Copied from Description"; "i"))
      )
      then del(.ticket.reproStepsMarkdown)
      else .
      end
  ' "$full_json" >"$out_json"

  jq -r '
    "# Work Item \(.ticket.id): \(.ticket.title)\n\n"
    + "- Type: \(.ticket.type)\n"
    + "- State: \(.ticket.state)\n"
    + "- URL: \(.metadata.htmlUrl)\n"
    + (if (.ticket.tags | length) > 0 then "- Tags: \(.ticket.tags | join(", "))\n" else "" end)
    + "\n## Ticket\n\n"
    + (if (.ticket.markdown | length) > 0 then .ticket.markdown else "_No description_" end)
    + (if .ticket.reproStepsMarkdown? then "\n\n## Repro Steps\n\n\(.ticket.reproStepsMarkdown)" else "" end)
    + "\n\n## Comments\n\n"
    + (
        if (.comments | length) == 0
        then "_No comments_\n"
        else (
          .comments
          | map("### Comment \(.id) - \(.author) - \(.createdDate)\n\n\(.markdown)")
          | join("\n\n")
        ) + "\n"
        end
      )
    + "\n## Attachments\n\n"
    + (
        if (.attachments | length) == 0
        then "_No attachments_\n"
        else (
          .attachments
          | map(
              if .status == "downloaded" then
                "- \(.name) (`\(.localPath)`; origin: \(.origin_kind)"
                + (if (.attachment_id != null and .attachment_id != "") then "; id: \(.attachment_id)" else "" end)
                + (if (.sizeBytes != null) then "; size: \(.sizeBytes) bytes" else "" end)
                + ")"
              else
                "- **[FAILED]** \(.name) (origin: \(.origin_kind); download failed)"
              end
            )
          | join("\n")
        ) + "\n"
        end
      )
  ' "$out_json" >"$out_md"
}

build_llm_brief() {
  local context_json="$1"
  local out_brief="$2"

  jq -r '
    # Sort comments chronologically (oldest first), keep first 3
    (.comments | sort_by(.createdDate) | .[0:3]) as $early_comments
    |
    # Strip base64 data URIs from markdown (they bloat context)
    def strip_base64:
      gsub("!\\[[^\\]]*\\]\\(data:image/[^)]+\\)"; "[inline image removed]")
      | gsub("!\\[[^\\]]*\\]\\(https://[^)]+\\)"; "[screenshot]");

    "# Work Item \(.ticket.id): \(.ticket.title)\n\n"
    + "- Type: \(.ticket.type)\n"
    + "- State: \(.ticket.state)\n"
    + "- URL: \(.metadata.htmlUrl)\n"
    + (if (.ticket.tags | length) > 0 then "- Tags: \(.ticket.tags | join(", "))\n" else "" end)
    + "\n---\n\n## Description\n\n"
    + (if (.ticket.markdown | length) > 0 then (.ticket.markdown | strip_base64) else "_No description_" end)
    + (if .ticket.reproStepsMarkdown? then "\n\n## Repro Steps\n\n" + (.ticket.reproStepsMarkdown | strip_base64) else "" end)
    + "\n\n---\n\n## Key Communications (\($early_comments | length) earliest of \(.comments | length) total)\n\n"
    + (
        if ($early_comments | length) == 0
        then "_No comments_\n"
        else (
          $early_comments
          | map("### \(.author) — \(.createdDate)\n\n" + (.markdown | strip_base64))
          | join("\n\n")
        ) + "\n"
        end
      )
    + "\n---\n\n## Attachments\n\n"
    + (
        if (.attachments | length) == 0
        then "_None_\n"
        else (
          (.attachments | map(select(.status == "downloaded"))) as $ok
          | (.attachments | map(select(.status != "downloaded"))) as $failed
          | (
              if ($ok | length) > 0 then
                ($ok | map("- \(.name) (`\(.localPath)`)") | join("\n")) + "\n"
              else ""
              end
            )
          + (
              if ($failed | length) > 0 then
                "\n**Warning:** \($failed | length) attachment(s) failed to download:\n"
                + ($failed | map("- **[FAILED]** \(.name)") | join("\n")) + "\n"
              else ""
              end
            )
        )
        end
      )
    + "\n---\n_Full ticket with all \(.comments | length) comments available in llm-context.md_\n"
  ' "$context_json" | tr -d '\r' >"$out_brief"
}

need_cmd curl
need_cmd jq
need_cmd awk
need_cmd sed

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

need_env ADO_PAT
need_env ADO_ORG
need_env ADO_PROJECT

WORK_ITEM_ID="${1:-${ADO_ID:-}}"
if [ -z "$WORK_ITEM_ID" ]; then
  echo "Missing work item input. Pass work item ID/URL as first arg or set ADO_ID." >&2
  usage
  exit 1
fi
WORK_ITEM_ID="$(resolve_work_item_id "$WORK_ITEM_ID")"

PROJECT_PATH="${ADO_PROJECT// /%20}"
# Support both URL formats: ADO_BASE_URL override, or auto-detect
if [ -n "${ADO_BASE_URL:-}" ]; then
  BASE_URL="${ADO_BASE_URL}/${PROJECT_PATH}"
elif [ -n "${ADO_USE_VSCOM:-}" ]; then
  BASE_URL="https://${ADO_ORG}.visualstudio.com/${PROJECT_PATH}"
else
  BASE_URL="https://dev.azure.com/${ADO_ORG}/${PROJECT_PATH}"
fi
OUT_ROOT="${ADO_OUT_DIR:-$(pwd)}"
TICKET_DIR="${OUT_ROOT}/workitem-${WORK_ITEM_ID}-full"
RAW_DIR="${TICKET_DIR}/raw"
ATTACH_DIR="${TICKET_DIR}/attachments"

if [ -d "$TICKET_DIR" ]; then
  rm -rf "$TICKET_DIR"
fi

mkdir -p "$RAW_DIR" "$ATTACH_DIR"

echo "Fetching work item ${WORK_ITEM_ID} from ${ADO_ORG}/${ADO_PROJECT} ..."
curl_json "${BASE_URL}/_apis/wit/workitems/${WORK_ITEM_ID}?%24expand=All&api-version=7.1" "${RAW_DIR}/workitem.json"
fetch_comments "${RAW_DIR}/comments.json"
fetch_skip_paged_collection "updates" "${RAW_DIR}/updates.json"
fetch_skip_paged_collection "revisions" "${RAW_DIR}/revisions.json"
fetch_linked_workitems "${RAW_DIR}/linked-workitems.json"

manifest_file="${RAW_DIR}/attachments-manifest.tsv"
build_attachment_manifest "$manifest_file"
download_attachments "$manifest_file" "${RAW_DIR}/attachments.json"

jq -n \
  --arg fetchedAt "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
  --arg org "$ADO_ORG" \
  --arg project "$ADO_PROJECT" \
  --argjson id "$WORK_ITEM_ID" \
  --arg sourceUrl "${BASE_URL}/_workitems/edit/${WORK_ITEM_ID}" \
  --slurpfile workitem "${RAW_DIR}/workitem.json" \
  --slurpfile comments "${RAW_DIR}/comments.json" \
  --slurpfile updates "${RAW_DIR}/updates.json" \
  --slurpfile revisions "${RAW_DIR}/revisions.json" \
  --slurpfile linked "${RAW_DIR}/linked-workitems.json" \
  --slurpfile attachments "${RAW_DIR}/attachments.json" \
  '{
    metadata: {
      fetchedAtUtc: $fetchedAt,
      org: $org,
      project: $project,
      workItemId: $id,
      htmlUrl: $sourceUrl
    },
    workItem: $workitem[0],
    comments: $comments[0],
    updates: $updates[0],
    revisions: $revisions[0],
    linkedWorkItems: $linked[0],
    attachments: $attachments[0]
  }' >"${TICKET_DIR}/full-ticket.json"

build_llm_context \
  "${TICKET_DIR}/full-ticket.json" \
  "${TICKET_DIR}/llm-context.json" \
  "${TICKET_DIR}/llm-context.md"

# Extract and strip base64 data URIs from llm-context.md and llm-context.json.
# Embedded screenshots (data:image/png;base64,...) can be 50K+ characters each,
# bloating the markdown to 50K+ tokens. These are images pasted directly into the
# ticket HTML (not hosted as ADO attachments), so they are NOT caught by the
# attachment downloader. We save them as files first, then replace the inline
# base64 with local file references.
extract_and_strip_base64() {
  local md_file="$1"
  local json_file="$2"
  local attach_dir="$3"

  # Check if there are any base64 data URIs
  if ! grep -q 'data:image/' "$md_file" 2>/dev/null; then
    return 0
  fi

  echo "Extracting inline base64 images to attachments/ ..."

  # Find python command: prefer PYTHON_CMD env var (set by iq-plan from paths.md),
  # then try python3/python on PATH. On Windows, the Microsoft Store "App Execution
  # Aliases" intercept bare python/python3 and fail, so PYTHON_CMD is the reliable path.
  local pycmd=""
  if [ -n "${PYTHON_CMD:-}" ] && "$PYTHON_CMD" --version >/dev/null 2>&1; then
    pycmd="$PYTHON_CMD"
  elif command -v python3 >/dev/null 2>&1 && python3 --version >/dev/null 2>&1; then
    pycmd="python3"
  elif command -v python >/dev/null 2>&1 && python --version >/dev/null 2>&1; then
    pycmd="python"
  else
    echo "  WARNING: python not found — cannot extract base64 images. Stripping with sed instead." >&2
    # Fallback: just strip with sed, no image extraction
    sed -E 's/!\[([^]]*)\]\(data:image\/[^)]+\)/![\1](inline image removed — install python to extract)/g' \
      "$md_file" > "${md_file}.tmp" && mv "${md_file}.tmp" "$md_file"
    return 0
  fi

  # Combined: Extract base64 images to files AND strip from markdown in one pass.
  # Uses a non-greedy match up to the closing paren to avoid catastrophic backtracking
  # on 50K+ character base64 strings.
  $pycmd -c "
import re, base64, sys, os

md_file = sys.argv[1]
attach_dir = sys.argv[2]

md = open(md_file, 'r', encoding='utf-8').read()
idx = [0]

# Match ![any alt](data:image/TYPE;base64,DATA) — use non-greedy .*? won't work
# because ) could be in base64. Instead, match the data URI prefix, then grab
# everything up to the LAST ) on the same logical token. Since base64 doesn't
# contain ), we can safely use [^)]+ for the data portion.
pattern = r'!\[([^\]]*)\]\(data:image/(png|jpe?g|gif|bmp|webp);base64,([^)]+)\)'

def extract_and_replace(m):
    idx[0] += 1
    alt = m.group(1)
    ext = m.group(2)
    if ext == 'jpeg':
        ext = 'jpg'
    b64 = m.group(3).strip()
    fname = f'inline-{idx[0]}.{ext}'
    fpath = os.path.join(attach_dir, fname)
    try:
        raw = base64.b64decode(b64)
        with open(fpath, 'wb') as f:
            f.write(raw)
        print(f'  Saved {fname} ({len(raw)} bytes)')
    except Exception as e:
        print(f'  WARNING: Failed to decode {fname}: {e}', file=sys.stderr)
    return f'![{alt}](attachments/{fname})'

result = re.sub(pattern, extract_and_replace, md)

with open(md_file, 'w', encoding='utf-8') as f:
    f.write(result)

print(f'Extracted {idx[0]} inline image(s)')
" "$md_file" "$attach_dir" 2>&1

  # Step 2: Strip base64 from JSON too (jq operates on the structured data)
  if [ -f "$json_file" ]; then
    $pycmd -c "
import re, json, sys

jf = sys.argv[1]
data = json.load(open(jf, 'r', encoding='utf-8'))
pattern = r'!\[[^\]]*\]\(data:image/[^;]+;base64,[^)]+\)'
replacement = '![image](see attachments/ for extracted images)'

def strip(obj, keys):
    for k in keys:
        if k in obj and isinstance(obj[k], str):
            obj[k] = re.sub(pattern, replacement, obj[k])

strip(data.get('ticket', {}), ['markdown', 'reproStepsMarkdown'])
for c in data.get('comments', []):
    strip(c, ['markdown'])

with open(jf, 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print('  Stripped base64 from JSON')
" "$json_file" 2>&1
  fi
}

extract_and_strip_base64 \
  "${TICKET_DIR}/llm-context.md" \
  "${TICKET_DIR}/llm-context.json" \
  "${ATTACH_DIR}"

build_llm_brief \
  "${TICKET_DIR}/llm-context.json" \
  "${TICKET_DIR}/llm-context-brief.md"

echo "Done."
echo "Output directory: ${TICKET_DIR}"
echo "Merged payload: ${TICKET_DIR}/full-ticket.json"
echo "LLM payload: ${TICKET_DIR}/llm-context.json"
echo "LLM markdown: ${TICKET_DIR}/llm-context.md"
echo "LLM brief:    ${TICKET_DIR}/llm-context-brief.md"
