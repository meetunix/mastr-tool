#!/usr/bin/env bash
shopt -s nocasematch

# MASTR_CACHE: Main cache directory, must be big and works best on filesystems with transparent compression
# MASTR_CONCURRENCY: Number of parallel processes for import and export (default: CPU cores minus one)
# MASTR_FORCE_USING_EXISTING_DUMP: Force pipeline run without downloading dump
# MASTR_SKIP_IMPORT_AND_EXPORT: Skip database import (incl. UTM enrichment) and export (e.g. restart without touching database or exports)
# MARTIN_URL: Base URL of the tile server, its cache is purged after the import (empty = skip)

PYTHON="/mastr/.venv/bin/python3"

MASTR_CACHE="/mastr/cache"
MASTR_CACHE_DUMP="$MASTR_CACHE/dump"
MASTR_DUMP_FILE="$MASTR_CACHE/mastr-latest.zip"
# source URL and ETag of the downloaded dump: the zip may be imported later
# (force mode, retry of a failed run) and the pipeline must report the date
# and version of the dump it actually imported
MASTR_DUMP_URL_FILE="$MASTR_DUMP_FILE.url"
MASTR_DUMP_ETAG_FILE="$MASTR_DUMP_FILE.etag"
# marks a completely extracted dump: an interrupted unzip must not be imported
MASTR_DUMP_EXTRACTED_FILE="$MASTR_CACHE/dump.extracted"
# ETag of the last dump that completed the whole pipeline
ETAG_FILE="$MASTR_CACHE/etag.txt"

# fall back to one process on single-core systems (nproc - 1 would be 0)
MASTR_CONCURRENCY="${MASTR_CONCURRENCY:-$(( $(nproc) > 1 ? $(nproc) - 1 : 1 ))}"

SYSTEMD_ID="download-mastr.sh"

# tile sources published by Martin (db/tiles.sql): the cache is purged per source
MARTIN_SOURCES="wind solar biomasse wasser geothermie stromspeicher kernkraft verbrennung gaserzeuger gasspeicher gasverbraucher stromverbraucher"
EXPORT_DIR="/mastr/output/export"
IMPORT_TIMESTAMP_FILE="$EXPORT_DIR/import_timestamp"
DUMP_DATE_FILE="$EXPORT_DIR/dump_date"

if ! [[ "$MASTR_CONCURRENCY" =~ ^[1-9][0-9]*$ ]]; then
  echo "[$SYSTEMD_ID] [ERROR] MASTR_CONCURRENCY must be a positive integer, got: '$MASTR_CONCURRENCY'" >&2
  exit 1
fi

REQUIRED_ENVS=(
  MASTR_CACHE
  SYSTEMD_ID
  EXPORT_DIR
  MASTR_FORCE_USING_EXISTING_DUMP
  MASTR_SKIP_IMPORT_AND_EXPORT
)


log_info() {
    if [ -x "$(which systemd-cat)" ] ; then
        echo "$1" | systemd-cat -p info -t "$SYSTEMD_ID"
    else
        echo "[$SYSTEMD_ID] [INFO] $1"
    fi
}

log_warn () {
    if [ -x "$(which systemd-cat)" ] ; then
        echo "$1" | systemd-cat -p warning -t "$SYSTEMD_ID"
    else
        echo "[$SYSTEMD_ID] [WARN] $1"
    fi
}

log_err () {
    if [ -x "$(which systemd-cat)" ] ; then
        echo "$1" | systemd-cat -p emerg -t "$SYSTEMD_ID"
    else
        echo "[$SYSTEMD_ID] [ERROR] $1"
    fi
}

check_env_var() {
  value=${!env}
  if [[ -z $value ]] ; then
    log_err "$env not set or has empty value"
    exit 1
  fi
}

create_directory() {
  local dir_path="$1"

  if [ ! -d "$dir_path" ]; then
    log_info "Creating directory: $dir_path"
    out="$(mkdir -p "$dir_path" 2>&1)"
    check_ret_val $? "Failed to create directory $dir_path" "Successfully created directory $dir_path"
  else
    log_info "Directory already exists: $dir_path"
  fi
}

wait_time() {
  log_info "wait $1 seconds before proceeding"
  sleep $1
}

wait_random() {
  RAND_BACKUP=$(((RANDOM % $1 ) + 1))
  wait_time $RAND_BACKUP
}


check_ret_val() {

  return_value=$1
  error_prefix=$2
  output_message=$3

  if [ $return_value -eq 0 ]; then
    log_info "$output_message"
  else
    log_err "$error_prefix: $output_message"
    log_err "closing ..."
    exit 1
  fi

}


fetch_remote_info() {
  # sets mastr_url and remote_etag, returns the exit code of get_mastr_url.py
  # (0: new dump, 20: unchanged since the last successful pipeline run)
  local info ret_val
  info="$($PYTHON get_mastr_url.py --cache-dir "$MASTR_CACHE")"
  ret_val=$?
  mastr_url="$(sed -n 1p <<< "$info")"
  remote_etag="$(sed -n 2p <<< "$info")"
  return $ret_val
}

fetch_remote_info_or_exit() {
  fetch_remote_info
  local ret_val=$?
  if [[ $ret_val -ne 0 && $ret_val -ne 20 ]] || [[ -z $mastr_url ]] ; then
    check_ret_val 1 "error evaluating remote mastr version" "get_mastr_url.py returned $ret_val"
  fi
}

mastr_download() {
  # download to a temporary file: a failed or aborted transfer must not
  # destroy the last good dump
  local tmp_file
  tmp_file="$MASTR_CACHE/.$(basename "$MASTR_DUMP_FILE").tmp-$$"
  # remove downloads of interrupted runs (the pipeline is single-writer)
  rm -f "$MASTR_CACHE/.$(basename "$MASTR_DUMP_FILE").tmp-"*

  wait_random 10
  log_info "download new mastr-dump ($mastr_url)"
  # --fail: an HTTP error page must not be saved as dump
  # --speed-limit/--speed-time: abort a stalled transfer (less than 1 KB/s for 5 minutes)
  if ! curl --fail --silent --show-error --location \
      --connect-timeout 60 --speed-limit 1024 --speed-time 300 --retry 3 --retry-delay 60 \
      --output "$tmp_file" "$mastr_url" ; then
    rm -f "$tmp_file"
    check_ret_val 1 "error while downloading $mastr_url" "download failed"
  fi
  # a truncated transfer has no valid zip directory
  if ! out="$(unzip -l "$tmp_file" 2>&1 > /dev/null)" ; then
    rm -f "$tmp_file"
    check_ret_val 1 "error while downloading $mastr_url" "downloaded file is no valid zip archive: $out"
  fi

  # erase the metadata and the extracted files of the old dump before the
  # zip is replaced: an interrupted run must not import them as the new dump
  log_info "erase old dump files"
  out="$(rm -f "$MASTR_DUMP_URL_FILE" "$MASTR_DUMP_ETAG_FILE" "$MASTR_DUMP_EXTRACTED_FILE" $MASTR_CACHE_DUMP/* 2>&1)"
  check_ret_val $? "error while erasing old dump files" "old dump files erased"

  out="$(mv -f "$tmp_file" "$MASTR_DUMP_FILE" 2>&1)"
  check_ret_val $? "error while moving the downloaded dump to $MASTR_DUMP_FILE" "dump downloaded to $MASTR_DUMP_FILE"

  write_file_atomic "$mastr_url" "$MASTR_DUMP_URL_FILE" && write_file_atomic "$remote_etag" "$MASTR_DUMP_ETAG_FILE"
  check_ret_val $? "error while writing the dump metadata" "dump metadata written"
}

mastr_extract_dump(){

  if [ ! -f "$MASTR_DUMP_EXTRACTED_FILE" ] ; then
    log_info "unzip dump $MASTR_DUMP_FILE"
    # remove the remains of an interrupted unzip
    out="$(rm -f $MASTR_CACHE_DUMP/* 2>&1)"
    check_ret_val $? "error while erasing old dump files" "old dump files erased"
    out="$(unzip -qq $MASTR_DUMP_FILE -d $MASTR_CACHE_DUMP/ 2>&1)"
    check_ret_val $? "error while unzipping $MASTR_DUMP_FILE" "$out"
    touch "$MASTR_DUMP_EXTRACTED_FILE"
  else
    log_info "dump is already extracted to $MASTR_CACHE_DUMP"
  fi

}


mastr_db_import() {
  log_info "import mastr-dump into database"
  $PYTHON import_mastr.py --cleanup --concurrency "$MASTR_CONCURRENCY" --cache-dir $MASTR_CACHE $MASTR_CACHE_DUMP
  check_ret_val $? "error while importing to database" ""
}

mastr_csv_export() {
  log_info "export csv files to $EXPORT_DIR"
  $PYTHON export_mastr.py --force --concurrency "$MASTR_CONCURRENCY" $EXPORT_DIR
  check_ret_val $? "error while exporting csv files from database" ""
}

mastr_db_dump() {
  # write to a temporary file and move it into place afterwards: mv within
  # the same directory is an atomic rename, so readers (mastr-static) never
  # see a partially written dump
  local dump_file="$EXPORT_DIR/mastr-latest.sql"
  local tmp_file="$EXPORT_DIR/.mastr-latest.sql.tmp-$$"
  log_info "create database dump (pg_dump, zstd) at $dump_file"
  # --exclude-schema=tiles: the tile functions are deployment specific and are
  # recreated by every import. The PostGIS extension and the GiST indices on
  # the unit tables stay in the dump, so restoring it needs PostGIS (see
  # README) - excluding the extension would not help, the indices need it.
  if PGPASSWORD="${DB_PASSWORD:-password}" pg_dump \
    -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${DB_USER:-mastr}" -d "${DB_NAME:-mastr}" \
    --exclude-schema=tiles \
    --format=custom --compress=zstd --file="$tmp_file" ; then
    mv -f "$tmp_file" "$dump_file"
    check_ret_val $? "error while moving database dump" "database dump written to $dump_file"
  else
    rm -f "$tmp_file"
    check_ret_val 1 "error while creating database dump" "database dump not written"
  fi
}

mastr_tiles_purge() {
  # Martin keeps the tiles for tile_expiry (12h). Without this purge the map
  # would show the data of the previous import for up to that long. A failure
  # is not fatal: the TTL bounds the staleness, and the import must not fail
  # because the tile server is down.
  local source code failed=0 url
  if [[ -z $MARTIN_URL ]] ; then
    log_info "MARTIN_URL not set, skipping the tile cache purge"
    return 0
  fi
  url="${MARTIN_URL%/}" # a trailing slash would produce a double slash in the path
  for source in $MARTIN_SOURCES ; do
    code="$(curl --silent --show-error --connect-timeout 3 --max-time 10 --output /dev/null \
        --write-out '%{http_code}' --request DELETE "$url/cache/tiles.$source")"
    case $code in
      200) ;;
      # Martin has not discovered the source yet (first import, or a new layer
      # before the next reload): there is nothing to purge
      404) log_info "tiles.$source is not published yet, nothing to purge" ;;
      *)
        log_warn "error while purging the tile cache of tiles.$source (HTTP $code)"
        failed=$((failed + 1))
        ;;
    esac
  done
  if [ $failed -eq 0 ] ; then
    log_info "purged the tile cache of $MARTIN_URL"
  fi
}

mastr_import() {
  wait_time 10 # wait for some db initialization tasks
  start=$(date +%s)
  if [[ $MASTR_SKIP_IMPORT_AND_EXPORT =~ ^(yes|true)$ ]] ; then
    log_info "skip import and export (MASTR_SKIP_IMPORT_AND_EXPORT is set)"
  else
    mastr_db_import
    mastr_tiles_purge
    mastr_csv_export
    mastr_db_dump
  fi
  end=$(date +%s)
  log_info "pipeline took $(( (end - start) / 60 )) minutes"
}

write_file_atomic() {
  # write to a temporary file and rename it into place: the app reads these
  # files over HTTP and must never see a partially written file
  local content="$1"
  local target="$2"
  local tmp_file
  tmp_file="$(dirname "$target")/.$(basename "$target").tmp-$$"

  if printf '%s\n' "$content" > "$tmp_file" ; then
    mv -f "$tmp_file" "$target"
  else
    rm -f "$tmp_file"
    log_err "error while writing $target"
    return 1
  fi
}

write_dump_date_file() {

  if [[ $1 =~ ^https://.*\.de/.*_([0-9]{8})_.*\.zip$ ]] ; then
    date_stamp="${BASH_REMATCH[1]}"
    y=$(echo $date_stamp | cut -c 1-4)
    m=$(echo $date_stamp | cut -c 5-6)
    d=$(echo $date_stamp | cut -c 7-8)

    dump_date_stamp="$y-$m-$d"
    log_info "write dump-timestamp ($dump_date_stamp) to $DUMP_DATE_FILE"
    write_file_atomic "$dump_date_stamp" "$DUMP_DATE_FILE"

    log_info "write import-timestamp (current time) to $IMPORT_TIMESTAMP_FILE"
    write_file_atomic "$(date --iso-8601=minutes)" "$IMPORT_TIMESTAMP_FILE"
  fi
}

finish_pipeline_run() {
  # only reached after every pipeline step succeeded (check_ret_val exits on
  # errors): storing the ETag earlier would skip the retry of a failed run
  local dump_url dump_etag
  dump_url="$(cat "$MASTR_DUMP_URL_FILE" 2>/dev/null)"
  dump_etag="$(cat "$MASTR_DUMP_ETAG_FILE" 2>/dev/null)"

  # fallback for a dump downloaded without metadata: the date of the current
  # download URL (set by the caller) may be newer than the imported dump
  write_dump_date_file "${dump_url:-$mastr_url}"

  if [[ -n $dump_etag ]] ; then
    log_info "write ETag of the imported dump ($dump_etag) to $ETAG_FILE"
    write_file_atomic "$dump_etag" "$ETAG_FILE"
    check_ret_val $? "error while writing $ETAG_FILE" "ETag written"
  fi
}

check_env_vars() {
  ### check if required environment variables are set
  for env in "${REQUIRED_ENVS[@]}" ; do
    check_env_var env
  done
}

create_directories() {
  for dir in $MASTR_CACHE_DUMP $EXPORT_DIR ; do
    create_directory $dir
  done
}

cd /mastr || exit 4
check_env_vars
create_directories

# use already existing dump
if [[ $MASTR_FORCE_USING_EXISTING_DUMP =~ ^(yes|true)$ ]]; then
  log_info "no check for newer MASTR dump, using existing dump or downloading if not existing"
  if [ ! -f $MASTR_DUMP_FILE ] ; then
    log_info "local dump not found, downloading current MASTR dump file"
    fetch_remote_info_or_exit
    mastr_download
  elif [ ! -s "$MASTR_DUMP_URL_FILE" ] ; then
    log_info "source of $MASTR_DUMP_FILE is unknown (downloaded by an older version), the dump date is taken from the current download URL and may be wrong"
    # not fatal: the existing dump can be imported without the download page
    fetch_remote_info
    [[ -z $mastr_url ]] && log_info "current download URL not available, the dump date is not updated"
  fi
  mastr_extract_dump
  mastr_import
  finish_pipeline_run
  exit
fi

# enforce download if no dump exists
if [ ! -f $MASTR_DUMP_FILE ] ; then
  log_info "no local dump found, download current MASTR dump file"
  fetch_remote_info_or_exit
  mastr_download
  mastr_extract_dump
  mastr_import
  finish_pipeline_run
  exit
fi

# only download and run pipeline, if remote file is newer than the last
# successfully imported one (using etag)
fetch_remote_info
ret_val=$?
if [ $ret_val -eq 20 ] ; then
  log_info "MASTR source file has not been changed"
elif [ $ret_val -eq 0 ] ; then
  create_directories
  if [[ -n $remote_etag && "$(cat "$MASTR_DUMP_ETAG_FILE" 2>/dev/null)" == "$remote_etag" ]] ; then
    log_info "dump $remote_etag is already downloaded, retrying the failed pipeline run"
  else
    mastr_download
  fi
  mastr_extract_dump
  mastr_import
  finish_pipeline_run
else
  log_err "--- Error evaluating remote mastr version---"
fi
