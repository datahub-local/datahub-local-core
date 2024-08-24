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
export GIT_USER_NAME="Datahub.local Bot"
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
########################################

cd $CONFIG_DIR

echo "Init $SCRIPT_NAME"

echo "Configure SSH."
eval $(ssh-agent -s) > /dev/null && (cat $SSH_KEY && echo) | ssh-add -k -

if [[ ! -f ".HA_VERSION" ]]; then
    echo "Configuring git"

    echo "Removing all files from folder"

    rm -rf * .*

    git clone --quiet "$GIT_REPO" .

    echo "Copying initial auth_providers"

    cp auth_providers.init.yaml.tpl auth_providers.yaml
    mkdir lost+found
else
    echo "Home Assistant already initialized"
fi

echo "Finish $SCRIPT_NAME"
