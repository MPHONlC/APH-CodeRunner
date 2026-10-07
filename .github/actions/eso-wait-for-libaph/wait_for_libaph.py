import argparse
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.github.com'
ACTIVE = {'queued', 'in_progress', 'waiting', 'requested', 'pending'}


def get(url, token):
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'eso-wait-for-libaph', 'X-GitHub-Api-Version': '2022-11-28'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        return response.read().decode('utf-8', 'replace')


def still_busy(args, token, now):
    busy = []
    since = (now - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    for workflow in args.workflows.split():
        try:
            data = json.loads(get('%s/repos/%s/actions/workflows/%s/runs?per_page=30&created=%s' % (
                API, args.repo, workflow, urllib.parse.quote('>=' + since)), token))
        except urllib.error.HTTPError as err:
            if err.code == 404:
                continue
            raise
        active = [r for r in data.get('workflow_runs', []) if r.get('status') in ACTIVE]
        if active:
            busy.append('%s is %s (%s)' % (workflow, active[0]['status'], active[0].get('html_url', '')))
    return busy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True)
    parser.add_argument('--workflows', required=True)
    parser.add_argument('--timeout-minutes', type=float, default=120)
    parser.add_argument('--poll-seconds', type=float, default=30)
    args = parser.parse_args()
    token = os.environ.get('GH_TOKEN', '')
    if os.environ.get('GITHUB_REPOSITORY', '').lower() == args.repo.lower():
        print('This is %s itself, nothing to wait for.' % args.repo)
        return 0
    event = os.environ.get('GITHUB_EVENT_NAME', '')
    if event != 'schedule':
        print('Started by %s, not the daily schedule, so there is nothing to wait for; going on with what %s has published.' % (event or 'hand', args.repo))
        return 0
    deadline = time.time() + args.timeout_minutes * 60
    waited = False
    while True:
        now = datetime.datetime.now(datetime.timezone.utc)
        try:
            busy = still_busy(args, token, now)
        except Exception as err:
            print('::warning title=Could not read %s runs::%s. Going on with what %s has published now.' % (args.repo, err, args.repo))
            return 0
        if not busy:
            print('%s has no run queued or running%s; going on.' % (args.repo, ' after waiting' if waited else ''))
            return 0
        if time.time() >= deadline:
            print('::warning title=%s still busy::Waited %d minutes; going on with what %s has published now. %s'
                  % (args.repo, args.timeout_minutes, args.repo, '; '.join(busy)))
            return 0
        print('Waiting for %s: %s' % (args.repo, '; '.join(busy)))
        sys.stdout.flush()
        waited = True
        time.sleep(args.poll_seconds)


if __name__ == '__main__':
    sys.exit(main())
