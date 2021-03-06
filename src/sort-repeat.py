from __future__ import print_function, division
import argparse
import os

import numpy as np
import tensorflow as tf
from tensorflow.contrib.rnn import LSTMBlockCell
from tqdm import trange

# Training settings
parser = argparse.ArgumentParser(description='Addition task')
parser.add_argument('--sequence-length', type=int, default=15, metavar='N',
                    help='sequence length for training (default: 15)')
parser.add_argument('--hidden-size', type=int, default=512, metavar='N',
                    help='hidden size for training (default: 512)')
parser.add_argument('--batch-size', type=int, default=16, metavar='N',
                    help='input batch size for training (default: 16)')
parser.add_argument('--steps', type=int, default=2000000, metavar='N',
                    help='number of args.steps to train (default: 2000000)')
parser.add_argument('--log-interval', type=int, default=1000, metavar='N',
                    help='how many steps between each checkpoint (default: 1000)')
parser.add_argument('--start-step', default=0, type=int, metavar='N',
                    help='manual step number (useful on restarts) (default: 0)')
parser.add_argument('--lr', type=float, default=0.001, metavar='LR',
                    help='learning rate (default: 0.001)')
parser.add_argument('--resume', default='', type=str, metavar='PATH',
                    help='path to latest checkpoint (default: none)')
parser.add_argument('--dont-print-results', dest='print_results', action='store_false', default=True,
                    help='whether to use act')
parser.add_argument('--dont-log', dest='log', action='store_false', default=True,
                    help='whether to log')
parser.add_argument('--vram-fraction', default=1., type=float, metavar='x',
                    help='fraction of memory to use (default: 1)')
parser.add_argument('--ponder', type=int, default=3, metavar='N',
                    help='artificial ponder')

args = parser.parse_args()


def generate(args):
    x = np.zeros((args.batch_size, args.sequence_length*2, 2), dtype=float)
    x[:, args.sequence_length-1, 1] = 1
    t = np.random.randn(args.batch_size, args.sequence_length)
    x[:, :args.sequence_length, 0] = t
    x = np.repeat(x, args.ponder, axis=1)
    binary_flag = np.zeros((args.batch_size, args.ponder*2*args.sequence_length, 1))
    binary_flag[:, ::args.ponder, :] = 1
    x = np.concatenate((binary_flag, x), axis=2)
    y = np.argsort(t, axis=1)
    return x, y.reshape(-1)


def main():
    args = parser.parse_args()

    input_size = 2
    output_size = args.sequence_length
    batch_size = args.batch_size
    hidden_size = args.hidden_size

    # Placeholders for inputs.
    x = tf.placeholder(tf.float32, [batch_size, args.ponder*2*args.sequence_length, 1+input_size])
    y = tf.placeholder(tf.int64, batch_size*args.sequence_length)

    rnn = LSTMBlockCell(hidden_size)
    output, final_state = tf.nn.dynamic_rnn(rnn, x, dtype=tf.float32)

    output = output[:, args.ponder-1::args.ponder, :]
    output = tf.reshape(output[:, args.sequence_length:, :], [-1, hidden_size])
    softmax_w = tf.get_variable("softmax_w", [hidden_size, output_size])
    softmax_b = tf.get_variable("softmax_b", [output_size])
    logits = tf.matmul(output, softmax_w) + softmax_b

    loss = tf.nn.sparse_softmax_cross_entropy_with_logits(labels=y, logits=logits)

    loss = tf.reduce_mean(tf.reshape(loss, [batch_size, -1]), axis=1)

    loss = tf.reduce_mean(loss)
    tf.summary.scalar('Loss', loss)

    train_step = tf.train.AdamOptimizer(args.lr).minimize(loss)

    predicted = tf.argmax(logits, 1)
    correct_sequences = tf.cast(tf.reduce_all(tf.reshape(tf.equal(predicted, y),
                                [args.batch_size, args.sequence_length]), axis=1), tf.float32)
    accuracy = tf.reduce_mean(correct_sequences)
    tf.summary.scalar('Accuracy', accuracy)

    merged = tf.summary.merge_all()
    logdir = './logs/sort_test/LR={}_Pond={}'.format(args.lr, args.ponder)
    while os.path.isdir(logdir):
        logdir += '_'
    if args.log:
        writer = tf.summary.FileWriter(logdir)

    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=args.vram_fraction)
    with tf.Session(config=tf.ConfigProto(gpu_options=gpu_options)) as sess:
        sess.run(tf.global_variables_initializer())
        loop = trange(args.steps)
        for i in loop:
            batch = generate(args)

            if i % args.log_interval == 0:
                summary, step_accuracy, step_loss = sess.run([merged, accuracy, loss],
                                                             feed_dict={
                                                                 x: batch[0], y: batch[1]})
                if args.print_results:
                    loop.set_postfix(Loss='{:0.3f}'.format(step_loss),
                                     Accuracy='{:0.3f}'.format(step_accuracy))
            if args.log:
                writer.add_summary(summary, i)
            train_step.run(feed_dict={x: batch[0], y: batch[1]})


if __name__ == '__main__':
    main()
