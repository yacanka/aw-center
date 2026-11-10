"""Render all current scene narration, or just the named scenes; reruns reuse cached WAVs."""
import argparse
import json
import subprocess
import tempfile

from synthesize import ROOT, WORK, render


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenes', nargs='*')
    args = parser.parse_args()
    with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as manifest:
        subprocess.run(['node', 'tools/demo-video/record.mjs', 'list'], cwd=ROOT, stdout=manifest, check=True)
        manifest.seek(0)
        scenes = json.load(manifest)
    wanted = set(args.scenes)
    unknown = wanted.difference(scene['id'] for scene in scenes)
    if unknown:
        parser.error(f'Unknown scenes: {sorted(unknown)}')
    requests = [dict(text=beat['text'], pronunciation=beat.get('spoken'), output=beat['wav'])
                for scene in scenes if not wanted or scene['id'] in wanted for beat in scene['beats']]
    clips = render(requests)
    if not wanted:
        index = WORK / 'narration-index.json'
        index.write_text(json.dumps(clips, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(clips)} ses parçası, {sum(c["seconds"] for c in clips):.2f} saniye.')


if __name__ == '__main__':
    main()
