#!/usr/bin/python3

import math
from keras.models import Model
from keras.layers import Input, LSTM, CuDNNGRU, Dense, Embedding, Reshape, Concatenate, Lambda, Conv1D, Multiply, Bidirectional, MaxPooling1D, Activation
from keras import backend as K
from keras.initializers import Initializer
from mdense import MDense
import numpy as np
import h5py
import sys

rnn_units=64
pcm_bits = 8
pcm_levels = 2**pcm_bits
nb_used_features = 38

class PCMInit(Initializer):
    def __init__(self, gain=.1, seed=None):
        self.gain = gain
        self.seed = seed

    def __call__(self, shape, dtype=None):
        num_rows = 1
        for dim in shape[:-1]:
            num_rows *= dim
        num_cols = shape[-1]
        flat_shape = (num_rows, num_cols)
        if self.seed is not None:
            np.random.seed(self.seed)
        a = np.random.uniform(-1.7321, 1.7321, flat_shape)
        #a[:,0] = math.sqrt(12)*np.arange(-.5*num_rows+.5,.5*num_rows-.4)/num_rows
        #a[:,1] = .5*a[:,0]*a[:,0]*a[:,0]
        a = a + np.reshape(math.sqrt(12)*np.arange(-.5*num_rows+.5,.5*num_rows-.4)/num_rows, (num_rows, 1))
        return self.gain * a

    def get_config(self):
        return {
            'gain': self.gain,
            'seed': self.seed
        }

def new_wavernn_model():
    pcm = Input(shape=(None, 2))
    pitch = Input(shape=(None, 1))
    feat = Input(shape=(None, nb_used_features))
    dec_feat = Input(shape=(None, 32))
    dec_state = Input(shape=(rnn_units,))

    conv1 = Conv1D(16, 7, padding='causal', activation='tanh')
    pconv1 = Conv1D(16, 5, padding='same', activation='tanh')
    pconv2 = Conv1D(16, 5, padding='same', activation='tanh')
    fconv1 = Conv1D(128, 3, padding='same', activation='tanh')
    fconv2 = Conv1D(32, 3, padding='same', activation='tanh')

    if False:
        cpcm = conv1(pcm)
        cpitch = pconv2(pconv1(pitch))
    else:
        cpcm = pcm
        cpitch = pitch

    embed = Embedding(256, 128, embeddings_initializer=PCMInit())
    cpcm = Reshape((-1, 128*2))(embed(pcm))


    cfeat = fconv2(fconv1(feat))

    rep = Lambda(lambda x: K.repeat_elements(x, 160, 1))

    rnn = CuDNNGRU(rnn_units, return_sequences=True, return_state=True)
    rnn_in = Concatenate()([cpcm, rep(cfeat)])
    md = MDense(pcm_levels, activation='softmax')
    gru_out, state = rnn(rnn_in)
    ulaw_prob = md(gru_out)
    
    model = Model([pcm, feat], ulaw_prob)
    encoder = Model(feat, cfeat)
    
    dec_rnn_in = Concatenate()([cpcm, dec_feat])
    dec_gru_out, state = rnn(dec_rnn_in, initial_state=dec_state)
    dec_ulaw_prob = md(dec_gru_out)

    decoder = Model([pcm, dec_feat, dec_state], [dec_ulaw_prob, state])
    return model, encoder, decoder
