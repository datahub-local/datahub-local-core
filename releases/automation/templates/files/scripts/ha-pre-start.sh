#!/bin/bash

SCRIPT_NAME=${0##*/}
exec > >(tee /tmp/$SCRIPT_NAME.log) 2>&1
set -e

########################################
CONFIG_DIR=/config
GIT_REPO="git@github.com:datahub-local/datahub-local-home-assistant-config.git"
########################################

cd $CONFIG_DIR

if [[ ! -f ".HA_VERSION" ]]; then
    echo "Init pre_start"

    echo "Configuring git"

    git config --global user.email "bot@datahub-local.alvsanand.com"
    git config --global user.name "Datahub.local Bot"

    git config --global core.sshCommand "ssh -i $HOME/.ssh/ssh_gh_deploy_key -o IdentitiesOnly=yes -o 'StrictHostKeyChecking=no' -F /dev/null"

    echo "Cloning git repo"

    git clone --quiet "$GIT_REPO" .

    echo "Installing HACS"

    wget -O - https://get.hacs.xyz | bash -

    echo "Copying initial auth_providers"

    cp auth_providers.init.yaml.tpl auth_providers.yaml

    echo "Finish pre_start"
else
    echo "Home Assistant already initialized"
fi
