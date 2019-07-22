from tensorflow.python.keras.models import Model
from tensorflow.python.keras.layers import Dense, Bidirectional, CuDNNLSTM, Dropout, Embedding
from tensorflow.python.keras.activations import tanh
import tensorflow as tf



class Encoder(Model):
    def __init__(self, vocab_size, emb_dim, dropout, encode_dim, agents_num, layers_num):
        """
        Include Local Encoder and Contextual Encoder
        :param vocab_size: size of vocab
        :param emb_dim: embedding dim
        :param dropout: dropout keep rate
        :param encode_dim: encode dim
        :param agents_num: number of agents
        :param layers_num: number of layers, sum of Local and Contextual

        :return encoder output with shape: [agents, [batch_size, part_len, encode_dim]] outer is a list in python inner
            is a tensor
        """
        self.local_encoder = LocalEncoder(vocab_size,emb_dim, dropout,encode_dim,agents_num)

        self.context_encoder = ContextualEncoder(layers_num, agents_num, encode_dim, emb_dim)

        super(Encoder, self).__init__()

    def call(self, inputs):
        """
        :param inputs: source word id with shape [batch_size, sequence_length] which is word id
        :return: encoder output with shape: [agents, [batch_size, part_len, encode_dim]] outer is a list in python inner
            is a tensor
        """
        return self.context_encoder(
            self.local_encoder(
                inputs
            )
        )


class LocalEncoder(Model):
    def __init__(self, vocab_size, emb_dim, dropout, encode_dim, agents_num):
        super(LocalEncoder, self).__init__()
        self.vocab_size = vocab_size
        self.emb_dim = emb_dim
        self.dropout = dropout
        self.encode_dim = encode_dim
        self.agents_num = agents_num

        # bilstm
        self.bilstm = Bidirectional(CuDNNLSTM(self.encode_dim, return_sequences=True), merge_mode='concat')
        self.bilstm = Dropout(self.dropout)(self.bilstm)

        # define linear
        self.dense = Dense(self.encode_dim)

        embedding = Embedding(vocab_size, emb_dim)
        self.embedding = Dropout(self.dropout)(embedding)

    def call(self, inputs):
        local_encoder_outputs = []
        inputs_embedding = self.embedding(inputs)
        for agent_index in range(self.agents_num):
            part_sent = tf.slice(inputs_embedding, [0, 300*i, 0], [-1, 300, self.emb_dim])
            local_encoder_outputs.append(
                self.dense(
                    self.bilstm(part_sent)
                )
            )
        return local_encoder_outputs

class ContextualEncoder(Model):
    def __init__(self, layer_num, agents_num, encode_dim, emb_dim ,):
        super(ContextualEncoder, self).__init__()
        self.layer_num = layer_num
        self.agents_num = agents_num
        self.encode_dim = encode_dim
        self.emb_dim = emb_dim

        # define
        self._contextual_encoder = [ [] for _ in range(self.layer_num)]

        # W3 and W4 matrix in article

        self.w3 = tf.Variable(tf.random_normal(shape=[self.encode_dim, self.emb_dim]), dtype=tf.float32)
        self.w4 = tf.Variable(tf.random_normal(shape=[self.encode_dim, self.emb_dim]), dtype=tf.float32)

        # add a linear
        self.dense = Dense(self.encode_dim)

        # add bilstm
        self.bi_lstm = Bidirectional(CuDNNLSTM(self.encode_dim, return_sequences=True), merge_mode='concat')

    def call(self, local_encoder_outputs):
        for layer_index in range(self.layer_num):
            for agent_index in range(self.agents_num):
                z = tf.add_n(
                    [
                        tf.reshape(tf.slice(x, [-1, -1, 0], [1, 1, self.encode_dim]),
                                   [1, self.encode_dim]) for x in local_encoder_outputs
                    ]
                )

                z = z / (self.agents_num - 1)
                f = tanh(tf.matmul(local_encoder_outputs[agent_index], self.w3) + tf.matmul(z, self.w4))

                self._contextual_encoder[layer_index].append(
                    self.dense(
                        self.bi_lstm(f)
                    )
                )
        return self._contextual_encoder
