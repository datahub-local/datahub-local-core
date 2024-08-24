#!/bin/bash

SCRIPT_NAME=${0##*/}
exec > >(tee /tmp/$SCRIPT_NAME.log) 2>&1
set -e

########################################
CONFIG_DIR=/config
GIT_BRANCH="main"
########################################

cd $CONFIG_DIR

if [[ -n $(git status --porcelain) ]]; then
    echo "There are changes in configuration folder [$CONFIG_DIR]."

    git pull
    
    git add .

    echo "Creating commit with new changes."

    git commit -m "chore: update config files on `date +'%d-%m-%Y %H:%M:%S'`"

    echo "Pushing commit to remote."

    git push -u origin "$GIT_BRANCH"
else
    echo "No changes in configuration folder [$CONFIG_DIR]."
fi
