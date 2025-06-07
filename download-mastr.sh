#!/usr/bin/env bash
shopt -s nocasematch

# MASTR_CACHE: Main cache directory, must be big and works best on filesystems with transparent compression
# MASTR_FORCE: Force pipeline run without downloading dump

PYTHON="/mastr/.venv/bin/python3"

MASTR_CACHE="/mastr/cache"
MASTR_CACHE_ENRICHER="$MASTR_CACHE/enricher"
MASTR_CACHE_DUMP="$MASTR_CACHE/dump"
MASTR_DUMP_FILE="mastr-latest.zip"
MASTR_DUMP="$MASTR_CACHE_DUMP/$MASTR_DUMP_FILE"

SYSTEMD_ID="mastr-entrypoint"
EXPORT_DIR="/mastr/output"
IMPORT_TIMESTAMP_FILE="$EXPORT_DIR/import_timestamp"
DUMP_DATE_FILE="$EXPORT_DIR/dump_date"
DUMP_DATE="undef"

REQUIRED_ENVS=(
  MASTR_CACHE
  MASTR_DUMP
  SYSTEMD_ID
  EXPORT_DIR
  MASTR_NOT_CHECK_UPDATES
)


log_info() {
    if [ -x "$(which systemd-cat)" ] ; then
        echo "$1" | systemd-cat -p info -t "$SYSTEMD_ID"
    else
        echo "[$SYSTEMD_ID] [INFO] $1"
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


mastr_download() {

  wait_random 10
  log_info "download new mastr-dump ($mastr_url)"
  out="$(curl --silent $mastr_url > $MASTR_DUMP)"
  check_ret_val $? "error while downloading $mastr_url" "$out"

  cd $MASTR_CACHE
  log_info "erase old dump files"
  out="$(rm -f mastr-dump/*)"
  check_ret_val $? "error while erasing old dump files" "$out"

  log_info "unzip dump $MASTR_DUMP_FILE"
  out="$(unzip -qq $MASTR_DUMP_FILE -d mastr-dump/)"
  check_ret_val $? "error while unzipping $MASTR_DUMP_FILE" "$out"
}


mastr_db_import() {
  log_info "import mastr-dump into database"
  $PYTHON import_mastr.py --cleanup --concurrency $(nproc) --cache-dir $MASTR_CACHE $MASTR_CACHE_DUMP
  check_ret_val $? "error while importing to database" ""
}

mastr_db_enrichment() {
  log_info "enrich data in database"
  $PYTHON enrich_mastr.py --concurrency $(nproc) --cache-dir $MASTR_CACHE_ENRICHER
  check_ret_val $? "error while data enrichment" ""
}

mastr_csv_export() {
  log_info "export csv files to $EXPORT_DIR"
  $PYTHON export_mastr.py --force --concurrency $(nproc) $EXPORT_DIR
  check_ret_val $? "error while exporting csv files from database" ""
}

mastr_import() {
  wait_time 20 # wait for some db initialization tasks
  start=$(date +%s)
  mastr_db_import
  mastr_db_enrichment
  mastr_csv_export
  end=$(date +%s)
  log_info "import, enrichment and export took $(($end/60 - $start/60)) minutes"
}

write_dump_date_file() {

  if [[ $1 =~ ^https://.*\.de/.*_([0-9]{8})_.*\.zip$ ]] ; then
    date_stamp="${BASH_REMATCH[1]}"
    y=$(echo $date_stamp | cut -c 1-4)
    m=$(echo $date_stamp | cut -c 5-6)
    d=$(echo $date_stamp | cut -c 7-8)

    dump_date_stamp="$y-$m-$d"
    log_info "write dump-timestamp ($dump_date_stamp) to %DUMP_DATE_FILE"
    echo "$dump_date_stamp" > $DUMP_DATE_FILE

    log_info "write import-timestamp (current time) to %IMPORT_TIMESTAMP_FILE"
    date --iso-8601=minutes > $IMPORT_TIMESTAMP_FILE
  fi
}

check_env_vars() {
  ### check if required environment variables are set
  for env in "${REQUIRED_ENVS[@]}" ; do
    check_env_var env
  done
}

create_directories() {
  for dir in $MASTR_CACHE_DUMP $MASTR_CACHE_ENRICHER $EXPORT_DIR ; do
    create_directory $dir
  done
}

cd /mastr
check_env_vars

# use already existing dump
if [[ $MASTR_NOT_CHECK_UPDATES =~ ^yes|true$ ]]; then
  log_info "no check for newer MASTR dump, using existing dump"
  mastr_import
  exit
fi

# enforce download if no dump exists
if [ ! -f $MASTR_DUMP ] ; then
  log_info "no local dump found, download current MASTR dump file"
  create_directories
  mastr_url="$($PYTHON get_mastr_url.py --cache-dir $MASTR_CACHE 2>&1)"
  #echo $mastr_url
  mastr_download
  mastr_import
  write_dump_date_file "$mastr_url"
fi

# only download and run pipeline, if remote file is newer than local one (using etag)
mastr_url="$($PYTHON get_mastr_url.py --cache-dir $MASTR_CACHE)"
ret_val=$?
if [ $ret_val -eq 20 ] ; then
  log_info "MASTR source file has not been changed"
elif [ $ret_val -eq 0 ] || [ $MASTR_FORCE =~ ^yes|true$ ]; then
  create_directories
  if [ $ret_val -eq 0] ; then
    mastr_download
  fi # only download if file remote file is newer than local one
  mastr_import
  write_dump_date_file "$mastr_url"
else
  log_err "--- Error evaluating remote mastr version---"
fi

#write_dump_date_file "$mastr_url"
