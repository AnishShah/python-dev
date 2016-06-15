# Auditor for patch files
# Patches should be declared as text/plain (also .py files),
# independent of what the browser says, and
# the "patch" keyword should get set automatically.

import posixpath
import identify_patch
import os
import subprocess
import string
import random
import json
import requests

patchtypes = ('.diff', '.patch')
sourcetypes = ('.diff', '.patch', '.py')

def create_pull_request(db, head, base, issue_id, issue_title):
    endpoint = 'https://api.github.com/repos/AnishShah/cpython/pulls'
    access_token = os.environ['ACCESS_TOKEN']
    headers = {'Authorization': 'token {}'.format(access_token)}
    data = json.dumps({
            "title": "{}".format(issue_title),
            "body": "fixes issue {}".format(issue_id),
            "base": base, "head": head})
    response = requests.post(endpoint, headers=headers, data=data)
    if not response.ok:
        raise Exception('Error generating pull request')
    else:
        response_body = response.json()
        url = response_body['html_url']
        state = response_body['state']
        pr_id = db.github_pullrequest_url.create(url=url, state=state)
        issue_pr = db.issue.get(issue_id, 'github_pullrequest_urls')
        issue_pr.append(pr_id)
        db.issue.set(issue_id, github_pullrequest_urls=issue_pr)
        db.commit()

def git_command(command, path):
    process = subprocess.Popen(command, cwd=path, shell=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate()
    # err takes stdout
    # if err:
    #     raise Exception(err)

def git_workflow(db, issue_id, file_id):
    path = os.environ['GIT_PATH']
    versions = map(lambda id: (db.version.get(id, 'name'), db.version.get(id, 'order')),
                   db.issue.get(issue_id, 'versions'))
    title = db.issue.get(issue_id, 'title')
    commit_msg = 'Fixes issue {} : {}'.format(issue_id, title)
    if len(versions) == 0:
        parent_branch = "master"
    else:
        version = versions.pop()
        if version[1] == 1:
            parent_branch = "master"
        else:
            parent_branch = version[0].split()[1]
    branch_name = ''.join([random.choice(string.ascii_letters) for i in range(random.choice(range(10, 20)))])
    filename = db.file.get(file_id, 'name')
    content = db.file.get(file_id, 'content')
    fp = open(os.path.join(path, filename), 'wb')
    fp.write(content)
    fp.close()
    git_command("git checkout {}".format(parent_branch), path)
    git_command("git checkout -b {}".format(branch_name), path)
    git_command("git apply {}".format(filename), path)
    git_command("git add -A", path)
    git_command("git commit -m \"{}\"".format(commit_msg), path)
    git_command("git push origin {}".format(branch_name), path)
    git_command("git checkout {}".format(parent_branch), path)
    git_command("git branch -D {}".format(branch_name), path)
    create_pull_request(db, branch_name, parent_branch, issue_id, title)


def ispatch(file, types):
    return posixpath.splitext(file)[1] in types

def patches_text_plain(db, cl, nodeid, newvalues):
    if ispatch(newvalues['name'], sourcetypes):
        newvalues['type'] = 'text/plain'
        # git_workflow(newvalues)

def patches_keyword(db, cl, nodeid, newvalues):
    # Check whether there are any new files
    newfiles = set(newvalues.get('files',()))
    if nodeid:
        newfiles -= set(db.issue.get(nodeid, 'files'))
    # Check whether any of these is a patch
    newpatch = False
    for fileid in newfiles:
        if ispatch(db.file.get(fileid, 'name'), patchtypes):
            newpatch = True
            git_workflow(db, nodeid, fileid)
            break
    if newpatch:
        # Add the patch keyword if its not already there
        patchid = db.keyword.lookup("patch")
        oldkeywords = []
        if nodeid:
            oldkeywords = db.issue.get(nodeid, 'keywords')
            if patchid in oldkeywords:
                # This is already marked as a patch
                return
        if not newvalues.has_key('keywords'):
            newvalues['keywords'] = oldkeywords
        if patchid not in newvalues['keywords']:
            newvalues['keywords'].append(patchid)

def patch_revision(db, cl, nodeid, oldvalues):
    # there shouldn't be old values
    assert not oldvalues
    if not ispatch(cl.get(nodeid, 'name'), patchtypes):
        return
    revno = identify_patch.identify(db, cl.get(nodeid, 'content'))
    if revno:
        cl.set(nodeid, revision=str(revno))

def init(db):
    db.file.audit('create', patches_text_plain)
    db.file.react('create', patch_revision)
    db.issue.audit('create', patches_keyword)
    db.issue.audit('set', patches_keyword)
