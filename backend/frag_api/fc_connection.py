"""Private FC configuration and explicit GUI sub-selection. No secrets in API results."""
import base64
from dataclasses import replace
import json
import os
from pathlib import Path
import stat
import subprocess
from urllib.parse import urlsplit

from frag_api.errors import PluginValidationError, PolicyRejectedError
from frag_api.fc_reader import load_fc
from frag_api.request_spec import strict_json

KEYS = ('FINANCE_CORE_PLUGIN_API_URL', 'FINANCE_CORE_PLUGIN_UI_URL',
        'FINANCE_CORE_PLUGIN_READ_TOKEN', 'FINANCE_CORE_PLUGIN_RECORDS_JSON')


def checked_file(state, must_exist=True):
    path = Path(state) / 'fc.env'
    for node in (path, *path.parents):
        if node.is_symlink() or (node.exists() and getattr(node.lstat(), 'st_file_attributes', 0) & 0x400):
            raise PluginValidationError()
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16 * 1024:
            raise PluginValidationError()
    elif must_exist:
        raise PluginValidationError()
    return path


def private_acl(path, create=False):
    if os.name != 'nt':
        if create:
            path.chmod(0o600)
        info = path.stat()
        return info.st_uid == os.getuid() and not stat.S_IMODE(info.st_mode) & 0o077
    # Native Windows ACLs, hidden helper, no credentials in command arguments/stdout.
    script = """$ErrorActionPreference='Stop'; $p='PATH'; $me=[Security.Principal.WindowsIdentity]::GetCurrent().User;
$allowed=@($me.Value,'S-1-5-18','S-1-5-32-544');
CREATE
$acl=Get-Acl -LiteralPath $p;
if (-not $acl.AreAccessRulesProtected -or $acl.GetOwner([Security.Principal.SecurityIdentifier]).Value -notin $allowed) {exit 2};
foreach($r in $acl.GetAccessRules($true,$true,[Security.Principal.SecurityIdentifier])) {
 if($r.AccessControlType -eq 'Allow' -and $r.IdentityReference.Value -notin $allowed) {exit 2}
};
"""
    creation = """
$security=[Security.AccessControl.FileSecurity]::new(); $security.SetAccessRuleProtection($true,$false); $security.SetOwner($me);
foreach($sid in $allowed) {$security.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($sid),[Security.AccessControl.FileSystemRights]::FullControl,[Security.AccessControl.AccessControlType]::Allow))};
$stream=[IO.FileSystemAclExtensions]::Create([IO.FileInfo]::new($p),[IO.FileMode]::CreateNew,[Security.AccessControl.FileSystemRights]::FullControl,[IO.FileShare]::None,4096,[IO.FileOptions]::None,$security);
$stream.Dispose();
""" if create else ''
    script = script.replace('CREATE', creation).replace('PATH', str(path).replace("'", "''"))
    try:
        result = subprocess.run(['pwsh', '-NoProfile', '-EncodedCommand', base64.b64encode(script.encode('utf-16-le')).decode()],
            capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def prepare_configuration(state):
    path = checked_file(state, must_exist=False)
    if path.exists():
        if not private_acl(path):
            raise PluginValidationError()
        return {'created': False, 'readyToEdit': True}
    if os.name != 'nt':
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
    if not private_acl(path, create=True):
        raise PluginValidationError()
    # Empty template only. Never copy acceptance inputs or overwrite a saved connection.
    path.write_text(''.join(key + '=\n' for key in KEYS), encoding='utf-8')
    return {'created': True, 'readyToEdit': True}


def read_configuration(state):
    path = checked_file(state)
    if not private_acl(path):
        raise PluginValidationError()
    before = path.stat()
    try:
        values = {}
        for line in path.read_text('utf-8-sig').splitlines():
            if not line.strip() or line.startswith('#'):
                continue
            key, separator, value = line.partition('=')
            if not separator or key not in KEYS or key in values or not value or value != value.strip():
                raise PluginValidationError()
            values[key] = value
        values.setdefault(KEYS[1], 'http://127.0.0.1:5174')
        if set(values) != set(KEYS) or any(c.isspace() for c in values[KEYS[2]]) or not values[KEYS[2]].isascii():
            raise PluginValidationError()
        for key in KEYS[:2]:
            url = urlsplit(values[key])
            if (url.scheme != 'http' or url.hostname not in {'127.0.0.1', 'localhost'} or not url.port
                    or url.username or url.password or url.path not in {'', '/'} or url.query or url.fragment):
                raise PluginValidationError()
        selection = strict_json(values[KEYS[3]])
        if not isinstance(selection, dict) or len(selection) != 1:
            raise PluginValidationError()
        after = path.stat()
        if (before.st_mtime_ns, before.st_size, before.st_ino) != (after.st_mtime_ns, after.st_size, after.st_ino):
            raise PluginValidationError()
        return values
    except (OSError, ValueError, UnicodeError) as error:
        raise PluginValidationError() from error


def configured_reader(state, profile=None, *, require_file=False):
    path = checked_file(state, must_exist=False)
    before = path.stat() if path.exists() else None
    configuration = read_configuration(state) if path.exists() or require_file else None
    if profile is not None and profile.fc_selection is not None:
        if configuration is None:
            raise PluginValidationError()
        approved = profile.fc_selection
        if set(strict_json(configuration[KEYS[3]])) != {approved.workspace_id}:
            raise PluginValidationError()
        configuration = {**configuration, KEYS[3]: json.dumps({approved.workspace_id: approved.record_ids}, separators=(',', ':'))}
    reader = load_fc(Path(state) / 'plugins', configuration)
    if reader is not None and configuration is not None:
        def stamp():
            info = checked_file(state).stat()
            return info.st_mtime_ns, info.st_size, info.st_ino
        loaded_stamp = before.st_mtime_ns, before.st_size, before.st_ino
        def check():
            if stamp() != loaded_stamp:
                raise PluginValidationError()
        check()
        reader = replace(reader, configuration_check=check)
    secret = configuration[KEYS[2]] if configuration else os.environ.get(KEYS[2], '')
    return reader, (secret,)


def validate_selection(reader, profile):
    options = reader.connection_options()
    selected = profile.fc_selection
    if options['workspace']['id'] != selected.workspace_id:
        raise PolicyRejectedError()
    allowed = {item['id'] for item in options['items']}
    for record in selected.record_ids:
        key = record[len('finance-item:'):] if record.startswith('finance-item:') else 'report:' + record.split(':', 1)[0]
        if key not in allowed:
            raise PolicyRejectedError()


def ensure_bundled_reader(installation, state):
    from frag_api.fc_reader import install_fc, _checked_package
    archive = Path(installation) / 'resources/finance-core/finance-core-frag-plugin-v1.10.0.zip'
    if not archive.is_file():
        raise PluginValidationError()
    current = Path(state) / 'plugins/finance-core/current.json'
    if current.exists():
        if (any(node.is_symlink() or (node.exists() and getattr(node.lstat(), 'st_file_attributes', 0) & 0x400)
                for node in (current, *current.parents)) or not current.is_file()
                or current.stat().st_nlink != 1 or current.stat().st_size > 16 * 1024):
            raise PluginValidationError()
        value = json.loads(current.read_text('utf-8-sig'))
        if not isinstance(value, dict) or set(value) != {'enabled', 'version'} or type(value['enabled']) is not bool:
            raise PluginValidationError()
        if value.get('enabled') is False:
            return  # Preserve the explicit disable switch across upgrades.
        if value.get('version') == '1.10.0':
            if _checked_package(Path(state) / 'plugins', 'finance-core') is None:
                raise PluginValidationError()
            return
    install_fc(archive, Path(state))
