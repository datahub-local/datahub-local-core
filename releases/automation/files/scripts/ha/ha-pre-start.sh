#!/bin/bash

SCRIPT_NAME=${0##*/}
exec > >(tee /tmp/$SCRIPT_NAME.log) 2>&1
set -e

########################################
CONFIG_DIR=/config
SSH_KEY=/etc/ssh_gh_deploy_key

GIT_REPO="git@github.com:datahub-local/datahub-local-home-assistant-config.git"
GIT_BRANCH="main"
GIT_USER_EMAIL="bot@datahub-local.alvsanand.com"
GIT_USER_NAME="Datahub.local Bot"
GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
########################################

cd $CONFIG_DIR

echo "Init $SCRIPT_NAME"

if [[ ! -f "$HOME/.bashrc" ]]; then
    echo "Configuring git"

    echo "Configure bashrc."

    git config --global user.email "$GIT_USER_EMAIL"
    git config --global user.name "$GIT_USER_NAME"
    git config --global core.sshCommand "$GIT_SSH_COMMAND"

    cat >> $HOME/.bashrc <<EOF
eval \$(ssh-agent -s) > /dev/null && (cat $SSH_KEY && echo) | ssh-add -k -
EOF
fi

if [[ ! -f ".HA_VERSION" ]]; then
    source $HOME/.bashrc

    echo "Removing all files from folder"

    rm -rf * .*

    git clone --quiet "$GIT_REPO" .

    echo "Installing HACS"

    wget -O - https://get.hacs.xyz | bash -

    echo "Disable trusted_users"
    cp configuration.yaml configuration.yaml.old
    cat configuration.yaml.old | sed -r 's/#?(.+): +(.+) #ADMIN_ID/#\1: \2 #ADMIN_ID/g' > configuration.yaml
    
    mkdir lost+found
else
    echo "Home Assistant already initialized"
fi

echo "Finish $SCRIPT_NAME"
