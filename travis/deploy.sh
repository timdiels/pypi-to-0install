#!/usr/bin/env bash
set -o errexit -o nounset

if [ "$TRAVIS_BRANCH" != "new" ] #TODO master
then
  echo "Not deploying as the commit was made against branch '$TRAVIS_BRANCH', not master"
  exit 0
fi

git config user.name "Travis"
git config user.email "timdiels.m@gmail.com"
git add -A .
git commit --amend -m "Updated feeds"
git push -q --force origin gh-pages

