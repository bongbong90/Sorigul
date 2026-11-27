export const COLAB_NEW_NOTEBOOK_URL = 'https://colab.research.google.com/#create=true'

export const COLAB_BOOTSTRAP_LINES = [
  '%%bash',
  'set -eu',
  'work=$(mktemp -d)',
  'cd "$work"',
  'git init -q',
  'git fetch -q --depth=1 https://github.com/bongbong90/Sorigul.git 23c0429759e286566632f0155f1a4e4c6ee3c720',
  'git checkout -q --detach FETCH_HEAD',
  'python -m pip install -r colab/requirements.txt',
  'python colab/sorigul_colab_bootstrap.py',
] as const

export const COLAB_BOOTSTRAP_COMMANDS = COLAB_BOOTSTRAP_LINES.join('\n')
