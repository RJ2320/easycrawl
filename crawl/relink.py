"""Find missing project assets without changing the project until reviewed."""
import os
from pathlib import Path


def missing(project):
    items = []
    if project.source and not os.path.isfile(project.source):
        items.append(dict(key='source', label='Source spreadsheet', path=project.source))
    for label, path in project.logos.items():
        if path and not os.path.isfile(path):
            items.append(dict(key='logo:' + label, label=label, path=path))
    return items


def search(folder, items):
    names = {Path(item['path']).name.casefold() for item in items}
    found = {name: [] for name in names}
    for root, _, files in os.walk(folder):
        for name in files:
            if name.casefold() in found:
                found[name.casefold()].append(str(Path(root) / name))
    return {item['key']: sorted(found[Path(item['path']).name.casefold()]) for item in items}


def apply(project, items, replacements):
    for item in items:
        path = replacements.get(item['key'])
        if not path or not os.path.isfile(path):
            continue
        if item['key'] == 'source' and item['label'] == 'Source spreadsheet':
            project.source = path
        else:
            project.logos[item['label']] = path
