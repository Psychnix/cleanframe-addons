"""Tests for publish.sh, the commit step of .github/workflows/cleantv-wallpapers.yml. Each test builds a
bare origin, an owner clone and a shallow runner clone (as actions/checkout makes it) in a temporary
folder. Needs git and bash; no network."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / 'publish.sh'
BOT, MESSAGE = 'github-actions[bot]', 'Generate CleanTV wallpapers [skip ci]'
EMPTY = '{"api":1,"entries":[]}\n'
ONE = '{"api":1,"entries":[\n{"id":"aw-neu"}\n]}\n'


def find_bash(git):
    # On Windows the bash of Git for Windows, not the WSL launcher in System32.
    if os.name == 'nt' and git:
        for parent in Path(git).resolve().parents:
            if (parent / 'bin' / 'bash.exe').is_file():
                return str(parent / 'bin' / 'bash.exe')
    return shutil.which('bash')


class Publish(unittest.TestCase):
    def setUp(self):
        self.git_exe = shutil.which('git')
        self.bash = find_bash(self.git_exe)
        if not self.git_exe or not self.bash:
            self.skipTest('needs git and bash')
        self.temp = tempfile.TemporaryDirectory(prefix='cleantv-publish-')
        base = Path(self.temp.name)
        config = base / 'gitconfig'
        config.write_text('', encoding='utf-8')
        # Isolated from the user's and the system's Git configuration (signing, hooks, line endings).
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(GIT_CONFIG_GLOBAL=str(config), GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
        self.origin, self.owner, self.runner = base / 'origin.git', base / 'owner', base / 'runner'
        self.git(base, 'init', '-q', '--bare', '-b', 'main', str(self.origin))
        self.git(base, 'init', '-q', '-b', 'main', str(self.owner))
        self.git(self.owner, 'remote', 'add', 'origin', self.origin.as_uri())

    def tearDown(self):
        self.temp.cleanup()

    def git(self, cwd, *args, check=True):
        result = subprocess.run([self.git_exe, *args], cwd=cwd, env=self.env, capture_output=True, text=True, encoding='utf-8')
        if check:
            self.assertEqual(result.returncode, 0, ' '.join(args) + '\n' + result.stdout + result.stderr)
        return result.stdout

    def write(self, repo, files):
        for name, text in files.items():
            path = repo / name
            if text is None:
                shutil.rmtree(path) if path.is_dir() else path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode('utf-8'))

    def push_owner(self, message, files):
        """The owner (or a merged pull request) pushes a commit to main."""
        self.write(self.owner, files)
        self.git(self.owner, 'add', '-A')
        self.git(self.owner, '-c', 'user.name=Owner', '-c', 'user.email=owner@example.invalid', 'commit', '-q', '-m', message)
        self.git(self.owner, 'push', '-q', 'origin', 'HEAD:main')

    def checkout(self):
        """actions/checkout with ref: main: a depth-1 clone of the current tip."""
        self.git(self.temp.name, 'clone', '-q', '--depth', '1', '--branch', 'main', self.origin.as_uri(), str(self.runner))

    def publish(self):
        return subprocess.run([self.bash, SCRIPT.as_posix()], cwd=self.runner, env=self.env, capture_output=True, text=True, encoding='utf-8')

    def history(self):
        return self.git(self.origin, 'log', '--format=%an|%s', 'main').splitlines()

    def tip_files(self):
        return sorted(self.git(self.origin, 'diff-tree', '--no-commit-id', '--name-only', '-r', 'main').splitlines())

    def tree(self):
        return sorted(self.git(self.origin, 'ls-tree', '-r', '--name-only', 'main').splitlines())

    def seed(self, extra=None):
        files = {'README.md': 'Catalog\n', 'cleantv-wallpapers/index.json': EMPTY, 'cleantv-wallpapers/images/Neu.jpg': 'original'}
        files.update(extra or {})
        self.push_owner('Add a photo', files)

    def generator_output(self):
        """What generate.py leaves in the runner, plus an untracked file that must not be committed."""
        self.write(self.runner, {'cleantv-wallpapers/generated/aw-neu/image.jpg': 'jpeg', 'cleantv-wallpapers/index.json': ONE, 'stray.txt': 'not mine'})

    def test_commits_only_the_outputs_as_the_bot(self):
        self.seed()
        self.checkout()
        self.generator_output()
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.history(), [BOT + '|' + MESSAGE, 'Owner|Add a photo'])
        self.assertEqual(self.tip_files(), ['cleantv-wallpapers/generated/aw-neu/image.jpg', 'cleantv-wallpapers/index.json'])
        self.assertNotIn('stray.txt', self.tree())

    def test_unchanged_output_commits_nothing(self):
        self.seed()
        self.checkout()
        self.write(self.runner, {'stray.txt': 'not mine'})
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('The generated wallpapers did not change.', result.stdout)
        self.assertEqual(self.history(), ['Owner|Add a photo'])

    def test_removing_the_last_image_removes_the_generated_folder(self):
        self.seed({'cleantv-wallpapers/generated/aw-alt/image.jpg': 'old jpeg', 'cleantv-wallpapers/index.json': ONE})
        self.checkout()
        self.write(self.runner, {'cleantv-wallpapers/generated': None, 'cleantv-wallpapers/index.json': EMPTY})
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.history()[0], BOT + '|' + MESSAGE)
        self.assertEqual(self.tip_files(), ['cleantv-wallpapers/generated/aw-alt/image.jpg', 'cleantv-wallpapers/index.json'])
        self.assertFalse([name for name in self.tree() if name.startswith('cleantv-wallpapers/generated/')])

    def test_main_moved_during_the_run_the_output_is_replayed_onto_it(self):
        # A merged catalog change lands while the generator runs; it does not touch images/ or tools/,
        # so no newer run would regenerate the photo.
        self.seed()
        self.checkout()
        self.generator_output()
        self.push_owner('Update the catalog', {'README.md': 'Catalog, updated\n'})
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.history(), [BOT + '|' + MESSAGE, 'Owner|Update the catalog', 'Owner|Add a photo'])
        self.assertEqual(self.tip_files(), ['cleantv-wallpapers/generated/aw-neu/image.jpg', 'cleantv-wallpapers/index.json'])
        self.assertEqual(self.git(self.origin, 'show', 'main:README.md'), 'Catalog, updated\n')

    def test_a_conflicting_push_fails_visibly_and_leaves_no_rebase(self):
        self.seed()
        self.checkout()
        self.generator_output()
        self.push_owner('Edit the index by hand', {'cleantv-wallpapers/index.json': '{"api":1,"entries":[\n{"id":"aw-other"}\n]}\n'})
        result = self.publish()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('::error::Could not push the generated wallpapers; run this workflow again.', result.stdout)
        self.assertEqual(self.history(), ['Owner|Edit the index by hand', 'Owner|Add a photo'])
        git_dir = self.runner / '.git'
        self.assertFalse((git_dir / 'rebase-merge').exists() or (git_dir / 'rebase-apply').exists(), 'no rebase is left in progress')


if __name__ == '__main__':
    unittest.main(verbosity=2)
