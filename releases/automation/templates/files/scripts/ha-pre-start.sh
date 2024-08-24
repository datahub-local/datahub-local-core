#!/bin/bash

SCRIPT_NAME=${0##*/}
exec > >(tee /tmp/$SCRIPT_NAME.log) 2>&1
set -e

########################################
CONFIG_DIR=/config
########################################

mkdir -p $CONFIG_DIR && cd $CONFIG_DIR

if [[ -z "$( ls -A '.' )" ]]; then
    git config --global user.email "bot@datahub-local.alvsanand.com"
    git config --global user.name "Datahub.local Bot"

    git config --global core.sshCommand "ssh -i $HOME/.ssh/ssh_gh_deploy_key -o IdentitiesOnly=yes -o 'StrictHostKeyChecking=no' -F /dev/null"

    git clone --quiet "git@github.com:datahub-local/datahub-local-home-assistant-config.git" .

    wget -O - https://get.hacs.xyz | bash -

    cp auth_providers.init.yaml.tpl auth_providers.yaml
fi
