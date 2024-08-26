#!/bin/bash

SCRIPT_NAME=${0##*/}
exec > >(tee /tmp/$SCRIPT_NAME.log) 2>&1
set -e

########################################
CONFIG_DIR=/config
SSH_KEY=/etc/ssh_gh_deploy_key

GIT_REPO="git@github.com:datahub-local/datahub-local-home-assistant-config.git"
GIT_BRANCH="main"
export GIT_USER_EMAIL="bot@datahub-local.alvsanand.com"
export GIT_USER_NAME="Datahub.local Bot"
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
########################################

# Function to log messages with timestamps
log() {
    local message="$1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $message"
}

# Function to log messages with timestamps
activate_ssh() {
    log "Configure SSH."
    eval $(ssh-agent -s) > /dev/null && (cat $SSH_KEY && echo) | ssh-add -k -
}

# Function to display usage
usage() {
    log
    log "Usage: $0 --command {upload|restore|download} [--force]"
    exit 1
}

# Function to upload changes: pull, commit, and push
upload() {    
    git pull

    if [[ -n $(git status --porcelain) ]]; then
        log "There are some changes in repository."
        
        git add .

        log "Creating commit with new changes."

        git commit -m "chore: update config files on `date +'%d-%m-%Y %H:%M:%S'`"

        log "Pushing commit to remote."

        git push -u origin "$GIT_BRANCH"
    else
        log "No changes in repository."
    fi
}

# Function to restore: reset hard
restore() {
    log "Restore repository to remote."
    git reset --hard
}

# Function to download: pull (with optional force reset)
download() {
    if [[ "$FORCE" = true ]]; then
        log "Restore repository to remote."
        git reset --hard
    fi

    git pull
}

########################################

cd $CONFIG_DIR

log "Init $SCRIPT_NAME"

# Variables for the command and force option
COMMAND=""
FORCE=false

# Parse options
while [[ $# -gt 0 ]]; do
    case "$1" in
        --command)
            COMMAND="$2"
            shift 2
            ;;
        --force)
            FORCE=true
            shift
            ;;
        *)
            usage
            ;;
    esac
done

if [[ -z "$COMMAND" ]]; then
    log "ERROR: Invalid command $COMMAND"
    usage
    exit 1
fi

activate_ssh

case "$COMMAND" in
    upload)
        upload
        ;;
    restore)
        restore
        ;;
    download)
        download
        ;;
esac

echo "Finish $SCRIPT_NAME"