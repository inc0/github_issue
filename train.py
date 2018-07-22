import pandas as pd
import logging
import glob
import os
from ktext.preprocess import processor
from sklearn.model_selection import train_test_split
import dill as dpickle
import numpy as np

from seq2seq_utils import load_decoder_inputs, load_encoder_inputs, load_text_processor
import tensorflow as tf


data_dir = "/data/"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

data_file = data_dir + 'github_issues.csv'
use_sample_data=True

if not os.path.isfile(data_dir + "title_pp.dpkl"):
    if use_sample_data:
        training_data_size=2000
        traindf, testdf = train_test_split(pd.read_csv(data_file).sample(n=training_data_size),
        test_size=.10)
    else:
        itraindf, testdf = train_test_split(pd.read_csv(data_file),test_size=.10)

    print(f'Train: {traindf.shape[0]:,} rows {traindf.shape[1]:,} columns')
    print(f'Test: {testdf.shape[0]:,} rows {testdf.shape[1]:,} columns')

    train_body_raw = traindf.body.tolist()
    train_title_raw = traindf.issue_title.tolist()

    body_pp = processor(keep_n=8000, padding_maxlen=70)
    train_body_vecs = body_pp.fit_transform(train_body_raw)

    print('\noriginal string:\n', train_body_raw[0], '\n')
    print('after pre-processing:\n', train_body_vecs[0], '\n')

    title_pp = processor(append_indicators=True, keep_n=4500,
        padding_maxlen=12, padding ='post')

    # process the title data
    train_title_vecs = title_pp.fit_transform(train_title_raw)

    print('\noriginal string:\n', train_title_raw[0])
    print('after pre-processing:\n', train_title_vecs[0])

    # Save the preprocessor
    with open(data_dir + 'body_pp.dpkl', 'wb') as f:
        dpickle.dump(body_pp, f)

    with open(data_dir + 'title_pp.dpkl', 'wb') as f:
        dpickle.dump(title_pp, f)

    # Save the processed data
    np.save(data_dir + 'train_title_vecs.npy', train_title_vecs)
    np.save(data_dir + 'train_body_vecs.npy', train_body_vecs)

encoder_input_data, doc_length = load_encoder_inputs(data_dir + 'train_body_vecs.npy')
decoder_input_data, decoder_target_data = load_decoder_inputs(data_dir + 'train_title_vecs.npy')

num_encoder_tokens, body_pp = load_text_processor(data_dir + 'body_pp.dpkl')
num_decoder_tokens, title_pp = load_text_processor(data_dir + 'title_pp.dpkl')

#arbitrarly set latent dimension for embedding and hidden units
latent_dim = 300

##### Define Model Architecture ######

########################
#### Encoder Model ####
encoder_inputs = tf.keras.layers.Input(shape=(doc_length,), name='Encoder-Input')

# Word embeding for encoder (ex: Issue Body)
x = tf.keras.layers.Embedding(num_encoder_tokens, latent_dim, name='Body-Word-Embedding', mask_zero=False)(encoder_inputs)
x = tf.keras.layers.BatchNormalization(name='Encoder-Batchnorm-1')(x)

# Intermediate GRU layer (optional)
#x = GRU(latent_dim, name='Encoder-Intermediate-GRU', return_sequences=True)(x)
#x = BatchNormalization(name='Encoder-Batchnorm-2')(x)

# We do not need the `encoder_output` just the hidden state.
_, state_h = tf.keras.layers.GRU(latent_dim, return_state=True, name='Encoder-Last-GRU')(x)

# Encapsulate the encoder as a separate entity so we can just
#  encode without decoding if we want to.
encoder_model = tf.keras.Model(inputs=encoder_inputs, outputs=state_h, name='Encoder-Model')

seq2seq_encoder_out = encoder_model(encoder_inputs)

########################
#### Decoder Model ####
decoder_inputs = tf.keras.layers.Input(shape=(None,), name='Decoder-Input')  # for teacher forcing

# Word Embedding For Decoder (ex: Issue Titles)
dec_emb = tf.keras.layers.Embedding(num_decoder_tokens, latent_dim, name='Decoder-Word-Embedding', mask_zero=False)(decoder_inputs)
dec_bn = tf.keras.layers.BatchNormalization(name='Decoder-Batchnorm-1')(dec_emb)

# Set up the decoder, using `decoder_state_input` as _state.
decoder_gru = tf.keras.layers.GRU(latent_dim, return_state=True, return_sequences=True, name='Decoder-GRU')

# FIXME: seems to be running into this https://github.com/keras-team/keras/issues/9761
decoder_gru_output, _ = decoder_gru(dec_bn) # , initial_state=seq2seq_encoder_out)
x = tf.keras.layers.BatchNormalization(name='Decoder-Batchnorm-2')(decoder_gru_output)

# Dense layer for prediction
decoder_dense = tf.keras.layers.Dense(num_decoder_tokens, activation='softmax', name='Final-Output-Dense')
decoder_outputs = decoder_dense(x)

########################
#### Seq2Seq Model ####

#seq2seq_decoder_out = decoder_model([decoder_inputs, seq2seq_encoder_out])
seq2seq_Model = tf.keras.Model([encoder_inputs, decoder_inputs], decoder_outputs)

seq2seq_Model.compile(optimizer=tf.keras.optimizers.Nadam(lr=0.001), loss='sparse_categorical_crossentropy', metrics=['accuracy'])

estimator = tf.keras.estimator.model_to_estimator(keras_model=seq2seq_Model)

def input_fn(dataset=None):
    return [encoder_input_data, decoder_input_data], np.expand_dims(decoder_target_data, -1)


estimator.train(input_fn=input_fn, steps=20)
result = estimator.evaluate(input_fn=input_fn, steps=1)
print(result)
