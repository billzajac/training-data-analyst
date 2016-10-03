#!/usr/bin/env python
# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import math
import multiprocessing

import tensorflow as tf

import google.cloud.ml.features as features


# This reads TF records after preprocessing. Nothing to change here
def read_examples(input_files, batch_size, shuffle, num_epochs=None):
  thread_count = multiprocessing.cpu_count()

  # The minimum number of instances in a queue from which examples are drawn
  # randomly. The larger this number, the more randomness at the expense of
  # higher memory requirements.
  MIN_AFTER_DEQUEUE = 100

  # When batching data, the queue's capacity will be larger than the batch_size
  # by some factor. The recommended formula is (num_threads + a small safety
  # margin). For now, we use a single thread for reading, so this can be small.
  QUEUE_SIZE_MULTIPLIER = thread_count + 3

  # Convert num_epochs == 0 -> num_epochs is None, if necessary
  num_epochs = num_epochs or None

  # input_files could be a path to one file or a file pattern.
  input_file_names = tf.train.match_filenames_once(input_files)

  # Build a queue of the filenames to be read.
  filename_queue = tf.train.string_input_producer(input_file_names, num_epochs,
                                                  shuffle)
  options = tf.python_io.TFRecordOptions(
      compression_type=tf.python_io.TFRecordCompressionType.GZIP)
  example_id, encoded_example = tf.TFRecordReader(options=options).read_up_to(
      filename_queue, batch_size)

  if shuffle:
    capacity = MIN_AFTER_DEQUEUE + QUEUE_SIZE_MULTIPLIER * batch_size
    return tf.train.shuffle_batch([example_id, encoded_example], batch_size,
                                  capacity, MIN_AFTER_DEQUEUE,
                                  enqueue_many=True, num_threads=thread_count)
  else:
    capacity = QUEUE_SIZE_MULTIPLIER * batch_size
    return tf.train.batch([example_id, encoded_example],
                          batch_size, capacity=capacity,
                          enqueue_many=True, num_threads=thread_count)


def _print_shape(t, name):
  if t == None or t.get_shape() == None:
     print name, ' = None'
  else:
     print name, ' = ', t.get_shape().as_list()


def _create_fakekey(input_data):
   batchsize = tf.shape(input_data)[0]
   return tf.ones([batchsize], dtype=tf.float32)


# TaxiFeatures is a dictionary; pull Tensors from the dictionary, and create features
def create_inputs(metadata, input_data=None):
  with tf.name_scope('inputs'):
    if input_data is None:
      input_data = tf.placeholder(tf.string, name='input', shape=(None,))
    parsed = features.FeatureMetadata.parse_features(metadata, input_data)

    # [batchsize, 1] 
    plat = parsed['plat']
    plon = parsed['plon']
    dlat = parsed['dlat']
    dlon = parsed['dlon']
    dist_cyl = 1000*tf.sqrt( tf.square(tf.sub(plat, dlat)) + tf.square(tf.sub(plon, dlon)) )

    inputs = dist_cyl
    print 'inputs=',inputs.get_shape().as_list()
    return (input_data, inputs, tf.squeeze(parsed['fare_amount']),
            _create_fakekey(input_data)) # no key tf.identity(parsed['key']))

def inference(inputs, metadata, hyperparams):
  input_size = 1
  output_size = metadata.features['fare_amount']['size']
  
  inputs = tf.Print(inputs, data=[inputs], message='INPUT VALUES = ', first_n=5)
  nnoutput = tf.contrib.layers.fully_connected(inputs, output_size, activation_fn=None,
                                   biases_initializer=tf.constant_initializer(0.1))
  nnoutput = tf.Print(nnoutput, data=[nnoutput], message='PRED VALUES = ', first_n=5)
 
  return nnoutput


def loss(output, targets):
  output = tf.Print(output, data=[output], message='OUTPUT = ', first_n=5)
  targets = tf.Print(targets, data=[targets], message='TARGETS = ', first_n=5)
  loss = tf.sqrt(tf.reduce_mean(tf.square(output - targets)), name = 'loss') # RMSE
  return loss

def training(loss_op, learning_rate):
  with tf.name_scope('train'):
    tf.scalar_summary(loss_op.op.name, loss_op)
    global_step = tf.Variable(0, name='global_step', trainable=False)
    optimizer = tf.train.AdadeltaOptimizer(learning_rate)
    train_op = optimizer.minimize(loss_op, global_step)
    return train_op, global_step
