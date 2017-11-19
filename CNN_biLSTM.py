import numpy as np
import os
import sys
from utilities import *
from sklearn.model_selection import train_test_split
import matplotlib.pyplot as plt
from tensorflow.contrib import rnn

# import scipy.io as scipyio
# prepare data

X_train, labels_train, list_ch_train = read_data(data_path="/home/yoyomoon/PycharmProjects/LSTM_work/data/",
                                                 split="train")  # train
X_test, labels_test, list_ch_test = read_data(data_path="/home/yoyomoon/PycharmProjects/LSTM_work/data/",
                                              split="test")  # test

assert list_ch_train == list_ch_test, "Mistmatch in channels!"

# Standardize
X_train, X_test = standardize(X_train, X_test)

# train_validation_split
X_tr, X_vld, lab_tr, lab_vld = train_test_split(X_train, labels_train,
                                                stratify=labels_train, random_state=123)
# one_hot encoding
y_tr = one_hot(lab_tr)
y_vld = one_hot(lab_vld)
y_test = one_hot(labels_test)
# scipyio.savemat('HAR_info_mat.mat', {'X_tr': X_tr, 'X_vld': X_vld, 'lab_tr' :lab_tr, 'lab_vld' :lab_vld,
#                                      'X_test': X_test, 'labels_test': labels_test})
# Imports
import tensorflow as tf

lstm_size = 27  # 3 times the amount of channels
lstm_layers = 2  # Number of layers
batch_size = 600  # Batch size
seq_len = 128  # Number of steps
learning_rate = 0.0001  # Learning rate (default is 0.001)
epochs = 500

# Hyperparameters

# Fixed
n_classes = 6
n_channels = 9

# Define weights
weights = {
    # Hidden layer weights => 2*n_hidden because of forward + backward cells
    'out': tf.Variable(tf.random_normal([2 * lstm_size, n_classes]))
}
biases = {
    'out': tf.Variable(tf.random_normal([n_classes]))
}

### Construct the graph

graph = tf.Graph()

# Construct placeholders
with graph.as_default():
    inputs_ = tf.placeholder(tf.float32, [None, seq_len, n_channels], name='inputs')
    labels_ = tf.placeholder(tf.float32, [None, n_classes], name='labels')
    keep_prob_ = tf.placeholder(tf.float32, name='keep')
    learning_rate_ = tf.placeholder(tf.float32, name='learning_rate')

# build conv layers

# Convolutional layers
with graph.as_default():
    # (batch, 128, 9) --> (batch, 128, 18)
    conv1 = tf.layers.conv1d(inputs=inputs_, filters=18, kernel_size=2, strides=1,
                             padding='same', activation=tf.nn.relu)
    n_ch = n_channels * 2
# pass to lstm layer
with graph.as_default():
    # Construct the LSTM inputs and LSTM cells
    lstm_in = tf.transpose(conv1, [1, 0, 2])  # reshape into (seq_len, batch, channels)
    lstm_in = tf.reshape(lstm_in, [-1, n_ch])  # Now (seq_len*N, n_channels)

    # To cells
    lstm_in = tf.layers.dense(lstm_in, lstm_size, activation=None)  # or tf.nn.relu, tf.nn.sigmoid, tf.nn.tanh?

    # Open up the tensor into a list of seq_len pieces
    lstm_in = tf.split(lstm_in, seq_len, 0)

    # Add LSTM layers
    lstm_fw_cell = rnn.BasicLSTMCell(lstm_size, forget_bias=1.0)
    lstm_bw_cell = rnn.BasicLSTMCell(lstm_size, forget_bias=1.0)
    initial_state_bw = lstm_bw_cell.zero_state(batch_size, tf.float32)
    initial_state_fw = lstm_fw_cell.zero_state(batch_size, tf.float32)
# Define forward pass and cost function:

with graph.as_default():
    outputs, _, _ = rnn.static_bidirectional_rnn(lstm_fw_cell, lstm_bw_cell, lstm_in,
                                                     dtype=tf.float32, initial_state_bw=initial_state_bw,
                                                     initial_state_fw=initial_state_fw)

    # We only need the last output tensor to pass into a classifier
    # logits = tf.matmul(outputs[-1], weights['out']) + biases['out']
    # logits = logits+biases['out']
    logits = tf.layers.dense(outputs[-1], n_classes, name='logits')

    # Cost function and optimizer
    cost = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=logits, labels=labels_))
    # optimizer = tf.train.AdamOptimizer(learning_rate_).minimize(cost) # No grad clipping

    # Grad clipping
    train_op = tf.train.AdamOptimizer(learning_rate_)

    gradients = train_op.compute_gradients(cost)
    capped_gradients = [(tf.clip_by_value(grad, -1., 1.), var) for grad, var in gradients]
    optimizer = train_op.apply_gradients(capped_gradients)

    # Accuracy
    correct_pred = tf.equal(tf.argmax(logits, 1), tf.argmax(labels_, 1))
    accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32), name='accuracy')

# train the network

validation_acc = []
validation_loss = []

train_acc = []
train_loss = []

with graph.as_default():
    saver = tf.train.Saver()

with tf.Session(graph=graph) as sess:
    ## save graph computation
    tensorboard_dir = 'tensorboard/mnist'
    if not os.path.exists(tensorboard_dir):
        os.makedirs(tensorboard_dir)

    writer = tf.summary.FileWriter(tensorboard_dir)
    writer.add_graph(sess.graph)

    ##
    sess.run(tf.global_variables_initializer())
    iteration = 1

    for e in range(epochs):
        # Initialize
        bw_state = sess.run(initial_state_bw)
        fw_state = sess.run(initial_state_fw)

        # Loop over batches
        for x, y in get_batches(X_tr, y_tr, batch_size):

            # Feed dictionary
            feed = {inputs_: x, labels_: y, keep_prob_: 0.5,
                    initial_state_bw: bw_state, initial_state_fw: fw_state, learning_rate_: learning_rate}

            loss, state, acc = sess.run([cost, optimizer, accuracy], feed_dict=feed)
            train_acc.append(acc)
            train_loss.append(loss)

            # Print at each 5 iters
            if (iteration % 5 == 0):
                print("Epoch: {}/{}".format(e, epochs),
                      "Iteration: {:d}".format(iteration),
                      "Train loss: {:6f}".format(loss),
                      "Train acc: {:.6f}".format(acc))

            # Compute validation loss at every 25 iterations
            if (iteration % 25 == 0):

                # Initiate for validation set
                val_state_bw = sess.run(lstm_bw_cell.zero_state(batch_size, tf.float32))
                val_state_fw = sess.run(lstm_fw_cell.zero_state(batch_size, tf.float32))

                val_acc_ = []
                val_loss_ = []
                for x_v, y_v in get_batches(X_vld, y_vld, batch_size):
                    # Feed
                    feed = {inputs_: x_v, labels_: y_v, keep_prob_: 1.0, initial_state_bw: val_state_bw,
                            initial_state_fw: val_state_fw}

                    # Loss
                    loss_v, acc_v = sess.run([cost, accuracy], feed_dict=feed)

                    val_acc_.append(acc_v)
                    val_loss_.append(loss_v)

                # Print info
                print("Epoch: {}/{}".format(e, epochs),
                      "Iteration: {:d}".format(iteration),
                      "Validation loss: {:6f}".format(np.mean(val_loss_)),
                      "Validation acc: {:.6f}".format(np.mean(val_acc_)))

                # Store
                validation_acc.append(np.mean(val_acc_))
                validation_loss.append(np.mean(val_loss_))

            # Iterate
            iteration += 1
            saver.save(sess, "checkpoints-crnn/har.ckpt")

# Plot training and test loss
t = np.arange(iteration - 1)

plt.figure(figsize=(6, 6))
plt.plot(t, np.array(train_loss), 'r-', t[t % 25 == 0], np.array(validation_loss), 'b*')
plt.xlabel("iteration")
plt.ylabel("Loss")
plt.legend(['train', 'validation'], loc='upper right')
plt.show()

# Plot Accuracies
plt.figure(figsize=(6, 6))

plt.plot(t, np.array(train_acc), 'r-', t[t % 25 == 0], validation_acc, 'b*')
plt.xlabel("iteration")
plt.ylabel("Accuray")
plt.legend(['train', 'validation'], loc='upper right')
plt.show()

## Evaluate on test set

test_acc = []

with tf.Session(graph=graph) as sess:
    # Restore
    saver.restore(sess, tf.train.latest_checkpoint('checkpoints-crnn'))

    for x_t, y_t in get_batches(X_test, y_test, batch_size):
        feed = {inputs_: x_t,
                labels_: y_t,
                keep_prob_: 1}

        batch_acc = sess.run(accuracy, feed_dict=feed)
        test_acc.append(batch_acc)
    print("Test accuracy: {:.6f}".format(np.mean(test_acc)))
