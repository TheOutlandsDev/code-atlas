#!/usr/bin/env python3
"""Build an offline VSIX from an explicit runtime allowlist; no marketplace calls."""
import hashlib
import json
from pathlib import Path
import zipfile
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ['package.json', 'LICENSE', 'README.md', 'SECURITY.md', 'CONTRIBUTING.md', 'CHANGELOG.md', 'docs/configuration.md', 'docs/architecture.md', 'docs/reviewed-workspaces.md', 'docs/troubleshooting.md', 'extension/extension.js', 'extension/policy.js', 'extension/catalog.js', 'extension/readonly.js', 'extension/scanner.js', 'extension/tree.js', 'extension/reviewed.js', 'extension/media/app.js', 'extension/media/styles.css', 'extension/media/index.template.html', 'tools/scan.py', 'examples/policy.example.json']


def package():
    manifest = json.loads((ROOT / 'package.json').read_text())
    name = manifest['name']
    version = manifest['version']
    publisher = manifest['publisher']
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    destination = dist / (name + '-' + version + '.vsix')
    if destination.exists():
        raise ValueError('Build output exists; preserve it or choose a clean checkout')
    payload = {}
    for name in RUNTIME:
        file = ROOT / name
        if file.is_symlink() or not file.is_file():
            raise ValueError('Runtime allowlist file is absent or a symlink')
        payload['extension/' + name] = file.read_bytes()
    payload['[Content_Types].xml'] = b'<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="js" ContentType="application/javascript"/><Default Extension="css" ContentType="text/css"/><Default Extension="html" ContentType="text/html"/><Default Extension="py" ContentType="text/plain"/><Default Extension="md" ContentType="text/markdown"/><Default Extension="vsixmanifest" ContentType="text/xml"/><Default Extension="" ContentType="text/plain"/></Types>'
    payload['extension.vsixmanifest'] = ('''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011"><Metadata><Identity Language="en-US" Id="''' + escape(manifest['name']) + '" Version="' + escape(version) + '" Publisher="' + escape(publisher) + '''"/><DisplayName>''' + escape(manifest['displayName']) + '''</DisplayName><Description xml:space="preserve">''' + escape(manifest['description']) + '''</Description><License>extension/LICENSE</License><Categories>Other</Categories><Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="''' + escape(manifest['engines']['vscode']) + '''"/><Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="ui"/></Properties></Metadata><Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation><Dependencies/><Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets></PackageManifest>''').encode()
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in payload.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)
    print(destination.name + ' SHA256 ' + hashlib.sha256(destination.read_bytes()).hexdigest())
    return destination


if __name__ == '__main__':
    package()
