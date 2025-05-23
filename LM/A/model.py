import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import math
import numpy as np


class LM_RNN(nn.Module):
    def __init__(self, emb_size, hidden_size, output_size, pad_index=0, out_dropout=0.1, emb_dropout=0.1, n_layers=1):
        super(LM_RNN, self).__init__()
        # This Model learn: 
        # 1. The embedding layer that maps the token ids to vectors
        # 2. The RNN layer that learns the sequence of the tokens

        # 1. Token ids emdedding to vectors
        self.embedding = nn.Embedding(output_size, emb_size, padding_idx=pad_index)
       
        # 2. Pytorch's RNN layer: https://pytorch.org/docs/stable/generated/torch.nn.RNN.html
        self.rnn = nn.RNN(emb_size, hidden_size, n_layers, bidirectional=False, batch_first=True)   
        

        self.pad_token = pad_index
        # Linear layer to project the hidden layer to our output space 
        self.output = nn.Linear(hidden_size, output_size)
        
    def forward(self, input_sequence):
        emb = self.embedding(input_sequence)

        rnn_out, _  = self.rnn(emb)

        output = self.output(rnn_out).permute(0,2,1)
        return output 




class LM_LSTM(nn.Module):
    def __init__(self, emb_size, hidden_size, output_size, pad_index=0, out_dropout=0.1, emb_dropout=0.1, n_layers=1):
        super(LM_LSTM, self).__init__()

        # 1. Token ids emdedding to vectors
        self.embedding = nn.Embedding(output_size, emb_size, padding_idx=pad_index)
        
        # 2. Pytorch's RNN layer: https://pytorch.org/docs/stable/generated/torch.nn.RNN.html
        self.rnn = nn.LSTM(emb_size, hidden_size, n_layers, bidirectional=False, batch_first=True) 

        self.pad_token = pad_index
        # Linear layer to project the hidden layer to our output space 
        self.output = nn.Linear(hidden_size, output_size)
        
    def forward(self, input_sequence):
        emb = self.embedding(input_sequence)

        rnn_out, _  = self.rnn(emb)

        output = self.output(rnn_out).permute(0,2,1)
        return output 




class LM_LSTM_DO(nn.Module):
    def __init__(self, emb_size, hidden_size, output_size, pad_index=0, out_dropout=0.1, emb_dropout=0.1, n_layers=1):
        super(LM_LSTM_DO, self).__init__()

        # 1. Token ids emdedding to vectors
        self.embedding = nn.Embedding(output_size, emb_size, padding_idx=pad_index)
        self.emb_dropout = nn.Dropout(emb_dropout)  # Dropout after embedding
        
        # 2. Pytorch's RNN layer: https://pytorch.org/docs/stable/generated/torch.nn.RNN.html
        self.rnn = nn.LSTM(emb_size, hidden_size, n_layers, bidirectional=False, batch_first=True) 
        
        # Dropout before the final linear layer
        self.out_dropout = nn.Dropout(out_dropout)

        self.pad_token = pad_index
        # Linear layer to project the hidden layer to our output space 
        self.output = nn.Linear(hidden_size, output_size)
        
    def forward(self, input_sequence):
        emb = self.embedding(input_sequence)
        emb = self.emb_dropout(emb)  # Apply dropout after embedding

        rnn_out, _  = self.rnn(emb)
        rnn_out = self.out_dropout(rnn_out)  # Apply dropout before output layer

        output = self.output(rnn_out).permute(0,2,1)
        return output 


