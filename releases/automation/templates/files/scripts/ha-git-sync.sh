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
export GIT_SSH_COMMAND="eval \$(ssh-agent -s) > /dev/null && ssh-add $SSH_KEY && ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
########################################

cd $CONFIG_DIR

echo "Init $SCRIPT_NAME"

echo "Configure SSH."
eval $(ssh-agent -s) > /dev/null && ssh-add $SSH_KEY

echo "Fetching latest version."
git pull

if [[ -n $(git status --porcelain) ]]; then
    echo "There are some changes in configuration folder."
    
    git add .

    echo "Creating commit with new changes."

    git commit -m "chore: update config files on `date +'%d-%m-%Y %H:%M:%S'`"

    echo "Pushing commit to remote."

    git push -u origin "$GIT_BRANCH"
else
    echo "No changes in configuration folder."
fi

echo "Finish $SCRIPT_NAME"
