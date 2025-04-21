#!/usr/bin/env bash

MASTR_CACHE="/mnt/cache"
MASTR_DUMP_FILE="mastr-latest.zip"
MASTR_DUMP="$MASTR_CACHE/$MASTR_DUMP_FILE"
MASTR_TOOL_DIR="/opt/mastr-tool"

SYSTEMD_ID="mastr-download"
CSV_TARGET="/var/www/mastr-tool/static/exports"
IMPORT_TIMESTAMP_FILE="$CSV_TARGET/import_timestamp"
DUMP_DATE_FILE="$CSV_TARGET/dump_date"
DUMP_DATE="undef"

source "$MASTR_TOOL_DIR/.venv/bin/activate"

log_info() {
    if [ -x "$(which systemd-cat)" ] ; then
        echo "$1" | systemd-cat -p info -t "$SYSTEMD_ID"
    fi
}

log_err () {
    if [ -x "$(which systemd-cat)" ] ; then
        echo "$1" | systemd-cat -p emerg -t "$SYSTEMD_ID"
    fi
}

wait_random() {
  RAND_BACKUP=$(((RANDOM % $1 ) + 1))
  log_info "wait $RAND_BACKUP seconds before proceeding"
  sleep $RAND_BACKUP
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
  cd $MASTR_TOOL_DIR
  log_info "import mastr-dump into database"
  out="$(python3 import_mastr.py --silent --cleanup --concurrency $(nproc) $MASTR_CACHE/mastr-dump/)"
  check_ret_val $? "error while importing to database" "$out"
}

mastr_csv_export() {
  cd $MASTR_TOOL_DIR
  log_info "export csv files to $CSV_TARGET"
  out="$(python3 export_mastr.py --force $CSV_TARGET)"
  check_ret_val $? "error while exporting csv files from database" "$out"
}

mastr_import() {
  wait_random 20
  start=$(date +%s)
  mastr_download
  mastr_db_import
  mastr_csv_export
  end=$(date +%s)
  log_info "import took $(($end/60 - $start/60)) minutes"
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

# enforce download if no dump exists
if [ ! -f $MASTR_DUMP ] ; then
  mastr_url="$(python3 /opt/mastr-tool/get_mastr_url.py)"
  #echo $mastr_url
  mastr_import
  write_dump_date_file "$mastr_url"
fi

# only download, if remote file is newer than local one (using etag)
mastr_url="$(python3 /opt/mastr-tool/get_mastr_url.py)"
ret_val=$?
if [ $ret_val -eq 20 ] ; then
  log_info "MASTR source file has not been changed"
elif [ $ret_val -eq 0 ]; then
  mastr_import
  write_dump_date_file "$mastr_url"
else
  log_err "--- Error evaluating remote mastr version---"
fi

#write_dump_date_file "$mastr_url"
