"""
Wrapper for pretrained Deepbind
"""

import os
import math
import tarfile
import tempfile
import subprocess
import numpy as np
from .core import TextModel
from subprocess import PIPE
from spacy.tokens import Doc
from spacy.vocab import Vocab
from ..core import Task
from spacy.language import Language

DEEPBIND_CLASSES = ['NotBinding', 'Binding']
SEQ_FILE_EXTENSION = '.seq'
DNA_ALPHABET = ['T', 'C', 'G', 'A', 'U', 'N']


def sigmoid(x):
  return 1 / (1 + np.exp(-x))


def process_deepbind_stdout(deepbind_stdout):
    """
    Process the output assuming that there is only one input and one factor, i.e.
    the output has this format:
    
    <BOF>
    <FACTOR_ID>\n
    <binding_score>\n
    <EOF>

    Returns:
    Probability of binding, as sigmoid(binding score) 
    """
    return np.expand_dims(sigmoid(np.array(deepbind_stdout.splitlines()[1:]).astype(np.float)), axis=1)


def deepbind(factor_id, sequence_fpath, exec_path):
    process = subprocess.run([exec_path, factor_id, sequence_fpath], stdout=PIPE, stderr=PIPE)

    return process_deepbind_stdout(process.stdout)


def deepbind_on_sequences(factor_id, sequences_list, exec_path, tmp_folder=None):
    tmp_file = tempfile.mkstemp(dir=tmp_folder, suffix = SEQ_FILE_EXTENSION)[1]

    with open(tmp_file, 'w') as tmp_fh:
        tmp_fh.write('\n'.join([s.replace('\x00', '') if len(s.replace('\x00', '')) > 0 else np.random.choice(DNA_ALPHABET) for s in sequences_list]))

    return deepbind(factor_id, tmp_file, exec_path)


def create_DNA_language():
    accepted_values = DNA_ALPHABET
    vocab = Vocab(strings=accepted_values)

    def make_doc(sequence):
        sequence = sequence.replace(' ', '')
        if len(sequence) == 0:
            words = np.random.choice(accepted_values)
        else:
            words = list(sequence)
        return Doc(vocab, words=words, spaces=[False]*len(words))

    return Language(vocab, make_doc)


class DeepBind(TextModel):
    """
    Deepbind wrapper
    """
    def __init__(
        self, tf_factor_id='D00328.003', use_labels=True, filename='deepbind.tgz',
        origin='https://ibm.box.com/shared/static/ns9e7666kfjwvlmyk6mrh4n6sqjmzagm.tgz',
        *args, **kwargs
    ):
        """
        Constructor

        Args:
            tf_factor_id (str): ID of the transcription factor to classify against.
            use_labels (bool): if False, use logits insted of labels.
            filename (str): where to store the downloaded zip containing the model
            origin (str): link where to download the model from
        """
        super().__init__(
            Task.CLASSIFICATION, filename, origin, *args, **kwargs
        )
        self.tf_factor_id = tf_factor_id
        self.use_labels = use_labels
        # make sure the model is present
        self.save_dir = os.path.dirname(self.model_path)
        self.model_dir = os.path.join(
            self.save_dir,
            'deepbind'
        )
        if not os.path.exists(self.model_dir):
            with tarfile.open(self.model_path, 'r:gz') as model_tar:
                model_tar.extractall(self.save_dir)
        self.exec_path = os.path.join(self.model_dir, 'deepbind')

    def predict(self, sample, **kwargs):
        if not isinstance(sample, list):
            sample = [sample]            
        binding_probs = deepbind_on_sequences(self.tf_factor_id, sample, self.exec_path)
        if self.use_labels:
            return binding_probs.flatten() > 0.5
        else:
            return np.hstack([1. - binding_probs,  binding_probs])
