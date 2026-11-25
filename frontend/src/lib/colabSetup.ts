export const COLAB_NEW_NOTEBOOK_URL = 'https://colab.research.google.com/#create=true'

export const COLAB_BOOTSTRAP_LINES = [
  '!git clone https://github.com/bongbong90/Sorigul.git',
  '!cd Sorigul && pip install -r colab/requirements.txt',
  '!python Sorigul/colab/sorigul_colab_bootstrap.py',
] as const

export const COLAB_BOOTSTRAP_COMMANDS = COLAB_BOOTSTRAP_LINES.join('\n')
