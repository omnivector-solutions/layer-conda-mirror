import os
from subprocess import check_call
from pathlib import Path

from charmhelpers.core.templating import render
from charmhelpers.core.hookenv import config, open_port
from charmhelpers.core.host import service_running
from charms.reactive import (
        hook,
        when,
        when_any,
        when_not,
        set_flag,
        endpoint_from_flag,
)

from charms.layer import status, nginx
from charms.layer.venv import ENV_BIN


temp_dir = Path('/tmp/conda-packages')
target_dir = Path('/opt/conda_mirror')
update_pid_file = Path('/run/conda-mirror-update.pid')


@when('venv.ready')
@when_not('conda-mirror.initialized')
def init_conda_mirror():
    temp_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
    target_dir.mkdir(mode=0o755, parents=True, exist_ok=True)

    render_services()

    # enable timer
    check_call(['systemctl', 'enable', 'update-conda-mirror.timer'])

    # do initial sync
    check_call(['systemctl', 'start', 'update-conda-mirror.service'])

    open_port(config('port'))
    status.active('Conda mirror installed')
    set_flag('conda-mirror.initialized')


@when_any('config.changed.upstream_channel',
          'config.changed.platform',
          'config.changed.threads')
def render_services():
    render('update-conda-mirror.service',
           '/etc/systemd/system/update-conda-mirror.service', {
               'pid_file': str(update_pid_file),
               'env_bin': str(ENV_BIN),
               'upstream_channel': config('upstream_channel'),
               'target_dir': str(target_dir),
               'temp_dir': str(temp_dir),
               'platform': config('platform'),
               'threads': config('threads')
            })
    render('update-conda-mirror.timer',
           '/etc/systemd/system/update-conda-mirror.timer', {
               'interval': config('update_interval')
           })


@when('nginx.available')
@when_not('conda-mirror.nginx.configured')
def configure_web_server():
    nginx.configure_site('conda-mirror', 'conda-mirror-vhost.conf')
    status.active('Nginx configured')
    set_flag('conda-mirror.nginx.configured')


@when('website.available')
def configure_website():
    site = endpoint_from_flag('website.available')
    site.configure(port=config('port'))


@hook('update-status')
def update_status():
    if service_running('update-conda-mirror.service'):
        pkgs = [pkg for d in os.walk(str(temp_dir))
                for pkg in d[2] if pkg.endswith('.tar.bz2')]
        status.maint(f'Updating mirror - {len(pkgs)} packages downloaded')
    else:
        pkgs = [pkg for d in os.walk(str(target_dir))
                for pkg in d[2] if pkg.endswith('.tar.bz2')]
        status.active(f'Conda mirror ready - {len(pkgs)} packages')
