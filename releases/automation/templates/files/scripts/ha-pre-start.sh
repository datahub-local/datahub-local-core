#!/bin/bash

SCRIPT_NAME=${0##*/}
exec > >(tee /tmp/$SCRIPT_NAME.log) 2>&1
set -e

########################################
CONFIG_DIR=/config
GIT_REPO="git@github.com:datahub-local/datahub-local-home-assistant-config.git"
GIT_BRANCH="main"
########################################

cd $CONFIG_DIR

if [[ ! -f "$HOME/.ssh/ssh_gh_deploy_key" ]]; then
    cp /etc/ssh_gh_deploy_key $HOME/.ssh/ssh_gh_deploy_key
    chmod 400 $HOME/.ssh/ssh_gh_deploy_key
fi

if [[ ! -f ".HA_VERSION" ]]; then
    echo "Init pre_start"

    echo "Configuring git"

    git config --global user.email "bot@datahub-local.alvsanand.com"
    git config --global user.name "Datahub.local Bot"

    git config --global core.sshCommand "ssh -i $HOME/.ssh/ssh_gh_deploy_key -o IdentitiesOnly=yes -o 'StrictHostKeyChecking=no' -F /dev/null"

    echo "Cloning git repo"

    rm -Rf lost+found || true
    git clone --quiet "$GIT_REPO" .

    echo "Installing HACS"

    wget -O - https://get.hacs.xyz | bash -

    echo "Copying initial auth_providers"

    cp auth_providers.init.yaml.tpl auth_providers.yaml
    mkdir lost+found

    echo "Finish pre_start"
else
    echo "Home Assistant already initialized"
fi
