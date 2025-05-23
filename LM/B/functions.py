import math
import copy
import os
import torch

import numpy as np
import torch.nn as nn
import scipy.stats as st
import matplotlib.pyplot as plt

from tqdm import tqdm
from torch import optim
from functools import partial
from torch.utils.data import DataLoader

from utils import collate_fn
from model import LM_LSTM_WT, LM_LSTM_VD

# ------------------------------------------------------------------------------
# Function: train_loop
#
# Description:
#     Executes one full pass (epoch) of training over the provided dataset. 
#     For each sample, the function performs:
#         - Forward pass through the model
#         - Loss computation
#         - Backward pass to compute gradients
#         - Gradient clipping to prevent exploding gradients
#         - Parameter update via the optimizer
#
# Parameters:
#     data (iterable): A dataset or dataloader providing training samples.
#                      Each sample should be a dictionary containing:
#                          - "source": input token IDs (tensor)
#                          - "target": target token IDs (tensor)
#                          - "number_tokens": number of tokens in the target sequence
#     optimizer (torch.optim.Optimizer): The optimizer used for updating model parameters.
#     criterion (callable): The loss function used to compute the training loss.
#     model (nn.Module): The model being trained.
#     clip (float, optional): Maximum allowed norm for gradients. Used to prevent
#                             gradient explosion (default: 5).
#
# Returns:
#     avg_loss (float): The average loss across all tokens in the dataset.
# ------------------------------------------------------------------------------
def train_loop(data, optimizer, criterion, model, clip=5):
    model.train()
    loss_array = []
    number_of_tokens = []
    
    for sample in data:
        optimizer.zero_grad()               # Zeroing the gradient
        output = model(sample['source'])    # Forward pass: compute predicted outputs by passing inputs to the model
        
        loss = criterion(output, sample['target'])                  # Compute the loss
        loss_array.append(loss.item() * sample["number_tokens"])
        number_of_tokens.append(sample["number_tokens"])

        loss.backward() # Compute the gradient, deleting the computational graph
        # clip the gradient to avoid explosioning gradients
        torch.nn.utils.clip_grad_norm_(model.parameters(), clip)  

        optimizer.step() # Update the weights
    
    # return the average loss over the batch
    return sum(loss_array)/sum(number_of_tokens)



# ------------------------------------------------------------------------------
# Function: eval_loop
#
# Description: Evaluates the performance of a trained language model on a given dataset
# (typically the dev set). Computes key evaluation metrics such as:
#     - Perplexity (PPL)
#     - Average loss
#
# Parameters:
#     data (iterable): A dataset or dataloader providing evaluation samples.
#                      Each sample should be a dictionary with the following keys:
#                          - "source": input token IDs (tensor)
#                          - "target": target token IDs (tensor)
#                          - "number_tokens": number of tokens in the target sequence
#     eval_criterion (callable): The loss function used for evaluation (e.g., nn.CrossEntropyLoss).
#     model (nn.Module): The trained model to be evaluated.
#
# Returns:
#     ppl (float): Perplexity over the dataset.
#     loss_to_return (float): Average loss normalized by the number of tokens.
# ------------------------------------------------------------------------------
def eval_loop(data, eval_criterion, model):
    
    model.eval()
    loss_to_return = []
    loss_array = []
    number_of_tokens = []

    # softmax = nn.Softmax(dim=1) # Use Softmax if you need the actual probability
    with torch.no_grad(): # It used to avoid the creation of computational graph
        for sample in data:
            output = model(sample['source'])
            loss = eval_criterion(output, sample['target'])

            loss_array.append(loss.item())
            number_of_tokens.append(sample["number_tokens"])
            
    ppl = math.exp(sum(loss_array) / sum(number_of_tokens))
    loss_to_return = sum(loss_array) / sum(number_of_tokens)

    return ppl, loss_to_return



# ------------------------------------------------------------------------------
# Function: test_eval_loop
#
# Description: Evaluates the performance of a trained language model on a given dataset
# (typically the test set). Computes key evaluation metrics such as:
#     - Perplexity (PPL)
#     - Average loss
#     - Standard Error of the Mean (SEM) for both loss and perplexity
#     - 95% Confidence Intervals (CI) for both loss and perplexity
#
# Parameters:
#     data (iterable): A dataset or dataloader providing evaluation samples.
#                      Each sample should be a dictionary with the following keys:
#                          - "source": input token IDs (tensor)
#                          - "target": target token IDs (tensor)
#                          - "number_tokens": number of tokens in the target sequence
#     eval_criterion (callable): The loss function used for evaluation (e.g., nn.CrossEntropyLoss).
#     model (nn.Module): The trained model to be evaluated.
#
# Returns:
#     ppl (float): Perplexity over the dataset.
#     loss_to_return (float): Average loss normalized by the number of tokens.
#     sem_loss (float or None): Standard Error of the Mean for the normalized loss.
#     ci_loss (tuple or None): 95% Confidence Interval for the normalized loss.
#     sem_ppl (float or None): Standard Error of the Mean for the perplexity.
#     ci_ppl (tuple or None): 95% Confidence Interval for the perplexity.
# ------------------------------------------------------------------------------
def test_eval_loop(data, eval_criterion, model):
    
    model.eval()
    loss_to_return = []
    loss_array = []
    loss_array_norm = []
    number_of_tokens = []
    sem_loss = None
    sem_ppl = None
    ci_loss = None
    ci_ppl = None

    # softmax = nn.Softmax(dim=1) # Use Softmax if you need the actual probability
    with torch.no_grad(): # It used to avoid the creation of computational graph
        for sample in data:
            output = model(sample['source'])
            loss = eval_criterion(output, sample['target'])

            loss_array.append(loss.item())
            number_of_tokens.append(sample["number_tokens"])
            loss_array_norm.append(loss.item() / sample["number_tokens"])
            
    ppl = math.exp(sum(loss_array) / sum(number_of_tokens))
    loss_to_return = sum(loss_array) / sum(number_of_tokens)

    # Confidence interval for the loss
    losses = np.array(loss_array_norm)
    ppl_values = np.exp(losses)

    # SEM computation 
    sem_loss = st.sem(losses)  
    sem_ppl  = st.sem(ppl_values)
    # print('TEST SEM Loss:', sem_loss)
    # print('TEST SEM PPL:', sem_ppl)

    #CI computation
    ci_loss = st.t.interval(0.95, len(losses)-1, loc=np.mean(losses), scale=sem_loss)
    ci_ppl = (np.exp(ci_loss[0]), np.exp(ci_loss[1]))

    return ppl, loss_to_return, sem_loss, ci_loss, sem_ppl, ci_ppl



# ------------------------------------------------------------------------------
# Function: init_weights
#
# Description:
#     Initializes the weights of neural network modules with custom strategies. 
#     This function is typically called once at the beginning of training to ensure
#     stable and well-scaled weight initialization.
#     - For RNN-based layers (GRU, LSTM, RNN):
#         - Input-hidden weights (`weight_ih`) are initialized using Xavier Uniform
#         - Hidden-hidden weights (`weight_hh`) are initialized using Orthogonal initialization
#         - Biases are set to zero
#     - For Linear layers:
#         - Weights are initialized uniformly in the range [-0.01, 0.01]
#         - Biases are initialized to 0.01
#
# Parameters:
#     mat (nn.Module): The model or submodule whose parameters will be initialized.
#                      This function recursively applies initialization to all supported
#                      submodules within `mat`.
# ------------------------------------------------------------------------------
def init_weights(mat):
    for m in mat.modules():
        if type(m) in [nn.GRU, nn.LSTM, nn.RNN]:
            for name, param in m.named_parameters():
                if 'weight_ih' in name:
                    for idx in range(4):
                        mul = param.shape[0]//4
                        torch.nn.init.xavier_uniform_(param[idx*mul:(idx+1)*mul])
                elif 'weight_hh' in name:
                    for idx in range(4):
                        mul = param.shape[0]//4
                        torch.nn.init.orthogonal_(param[idx*mul:(idx+1)*mul])
                elif 'bias' in name:
                    param.data.fill_(0)
        else:
            if type(m) in [nn.Linear]:
                torch.nn.init.uniform_(m.weight, -0.01, 0.01)
                if m.bias != None:
                    m.bias.data.fill_(0.01)



# ------------------------------------------------------------------------------
# Function: path_define
#
# Description:
#     Constructs a descriptive and unique string identifier for saving model-relatedmartifacts. 
#     The identifier includes key hyperparameters to ensure easy traceability and reproducibility of experiments.
#
# Parameters:
#     LABEL (str): Identifier for the model or experiment.
#     LR (float): Learning rate used in training.
#     HID_SIZE (int): Size of the hidden layers in the model.
#     EMB_SIZE (int): Size of the embedding vectors.
#     BATCH_SIZE (int): Size of the training batches.
#     N_LAYERS (int): Number of layers in the model.
#     DROPOUT: Dropout rate
#     OPTIMIZER (str): Optimizer used for training (e.g., 'Adam', 'SGD').
#
# Returns:
#     path (str): A formatted string with all the hyperparameters embedded,
#                 suitable for use in filenames or directory paths.
# ------------------------------------------------------------------------------
def path_define(LABEL, LR, BATCH_SIZE, HID_SIZE, EMB_SIZE, N_LAYERS, DROPOUT, OPTIMIZER):
    path = f"{LABEL}_lr-{str(LR).replace('.', ',')}_hid-{HID_SIZE}_emb-{EMB_SIZE}_batch-{BATCH_SIZE}_layers-{N_LAYERS}"
    if DROPOUT is not None:
        path += f"_drop-{str(DROPOUT).replace('.', ',')}"
    path += f"_{OPTIMIZER}"
    return path



# ------------------------------------------------------------------------------
# Function: save_model
#
# Description:
#     Saves the state dictionary (model weights) of the provided model to a file
#     at the specified path. The file is saved in the 'bin' directory with a 
#     ".pt" extension. 
#
# Parameters:
#     model (nn.Module): The model whose state dictionary is to be saved.
#     path (str): The path that encode the hyperparameters of the model.
# ------------------------------------------------------------------------------
def save_model(model, path):
    path = f'bin/' + path + f'.pt'
    torch.save(model.state_dict(), path)



# ------------------------------------------------------------------------------
# Function: plot_training_progress
#
# Description:
#     Generates and saves two plots showing the evolution of training metrics:
#       1. Training and validation loss over sampled epochs
#       2. Validation perplexity (PPL) over sampled epochs
#
#     The plots are saved as a PNG file in the "plots/" directory. The filename
#     includes key hyperparameters (e.g., learning rate, dropout rates) for easy
#     identification of the experiment.
#
# Parameters:
#     sampled_epochs (list[int]): Epoch indices at which metrics were sampled.
#     losses_train (list[float]): Training loss values corresponding to the sampled epochs.
#     losses_dev (list[float]): Validation loss values corresponding to the sampled epochs.
#     ppl_dev_values (list[float]): Perplexity values on the validation set.
# ------------------------------------------------------------------------------
def plot_training_progress(sampled_epochs, losses_train, losses_dev, ppl_dev_values, path='PLOT'):
    
    fig, axes = plt.subplots(2, 1, figsize=(8, 10))
    font_size = 14  # Font size per labels, titoli, e legende

    # Primo grafico: Loss Function
    axes[0].plot(sampled_epochs, losses_train, linestyle='-', color='b', label='Training Loss')
    axes[0].plot(sampled_epochs, losses_dev, linestyle='-', color='r', label='Validation Loss')
    axes[0].set_xlabel('Epoche', fontsize=font_size)
    axes[0].set_ylabel('Loss', fontsize=font_size)
    axes[0].set_title('Loss Trend', fontsize=font_size + 2)
    axes[0].legend(fontsize=font_size)
    axes[0].grid(True, linestyle='--', alpha=0.6)
    axes[0].tick_params(axis='both', labelsize=font_size)

    axes[0].set_xlim(0, 100)
    axes[0].set_ylim(1, 9)

    # Secondo grafico: Perplexity
    axes[1].plot(sampled_epochs, ppl_dev_values, marker='s', linestyle='-', color='g', label='Validation PPL')
    axes[1].set_xlabel('Epoche', fontsize=font_size)
    axes[1].set_ylabel('Perplexity (PPL)', fontsize=font_size)
    axes[1].set_title('Perplexity Trend', fontsize=font_size + 2)
    axes[1].legend(fontsize=font_size)
    axes[1].grid(True, linestyle='--', alpha=0.6)
    axes[1].tick_params(axis='both', labelsize=font_size)

    axes[1].set_xlim(0, 100)
    y_max = 400
    if max(ppl_dev_values) > 500:
        y_max = max(ppl_dev_values)
    axes[1].set_ylim(50, y_max)

    fig.subplots_adjust(hspace=0.4)

    filepath = os.path.join('plots', path + '.png')
    plt.savefig(filepath, dpi=300)



# ------------------------------------------------------------------------------
# Function: get_last_experiment_id
#
# Description:
#     Retrieves the last experiment ID recorded in the `experiments.csv` file.
# ------------------------------------------------------------------------------
def get_last_experiment_id(filename):

    # Read existing file
    with open(filename, 'r') as f:
        lines = f.readlines()
        if len(lines) <= 1:
            return 0  # File exists but only header is present

        last_line = lines[-1].strip().split(',')

        try:
            return int(last_line[0])
        except ValueError:
            return 0  # If parsing fails, default to 0



# ------------------------------------------------------------------------------
# Function: save_experiment_results
#
# Description:
#     Appends a new row to the `experiments.csv` file, logging key details and
#     evaluation metrics from a trained model experiment. This includes model
#     configuration, optimizer, number of training epochs, and test set performance
#     such as perplexity, normalized loss, standard error, and confidence intervals.
#
# Parameters:
#     network_type (str): The type/name of the network architecture used.
#     lr (float): Learning rate used during training.
#     layers (int): Number of layers in the model.
#     batch_size (int): Size of the training batches.
#     hidden_size (int): Size of the hidden layers in the model.ù
#     emb_size (int): Dimensionality of the embedding layer.
#     dropout (float): Dropout rate 
#     optimizer (str): Optimizer used (e.g., 'Adam', 'SGD').
#     epoche (int): Number of epochs the model was trained.
#     test_ppl (float): Perplexity on the test set.
#     lest_loss_norm (float): Normalized test loss.
#     sem_loss (float): Standard Error of the Mean (SEM) for test loss.
#     ci_loss (tuple): 95% Confidence Interval for test loss.
#     sem_ppl (float): Standard Error of the Mean (SEM) for test perplexity.
#     ci_ppl (tuple): 95% Confidence Interval for test perplexity.
#
# Behavior:
#     - Automatically retrieves the last experiment ID and increments it.
#     - Creates the CSV file with a header if it does not exist.
#     - Appends all values (rounded to 2 decimals) to the file.
#
# Output:
#     A new line is added to 'experiments.csv' recording the current experiment.
# ------------------------------------------------------------------------------
def save_experiment_results(network_type, lr, layers, batch_size, hidden_size, emb_size, dropout, 
                            optimizer, epoche, test_ppl, lest_loss_norm, sem_loss, ci_loss, 
                            sem_ppl, ci_ppl):
    filename = 'experiments.csv'

    experiment_id = get_last_experiment_id(filename) + 1    # Leggi l'ultimo ID
    file_exists = os.path.isfile(filename)                  # Check if the file exists  
    
    # print("File exists: ", file_exists)
    # If the file does not exist, create it and write the header
    with open(filename, 'a') as f:
        f.write(f'{experiment_id},{network_type},{lr},{layers},{batch_size},{hidden_size},{emb_size},{dropout},{optimizer},{epoche},{round(test_ppl, 2)},{round(lest_loss_norm, 2)},{round(sem_loss, 2)},{round(ci_loss[0], 2)}-{round(ci_loss[1], 2)},{round(sem_ppl, 2)},{round(ci_ppl[0], 2)}-{round(ci_ppl[1], 2)}\n')



# ------------------------------------------------------------------------------
# Function: train_model
#
# Description:
#     Trains a language model (LM) using the Penn Treebank dataset with
#     specified hyperparameters. Handles full pipeline from data preprocessing,
#     model initialization, training loop with early stopping, and evaluation.
#     Also manages logging, saving the best-performing model, and visualizing
#     training metrics such as loss and perplexity.
#
# Parameters:
#     train_dataset (Dataset): Training dataset containing tokenized sentences.
#     dev_dataset (Dataset): Validation dataset containing tokenized sentences.
#     test_dataset (Dataset): Test dataset for final evaluation of the model.
#     lang (Lang): Language object containing vocabulary mapping (word2id, id2word).
#     BATCH_SIZE (int): Number of samples per training batch.
#     HID_SIZE (int): Size of the RNN hidden layers.
#     EMB_SIZE (int): Dimensionality of word embeddings.
#     LR (float): Learning rate used by the optimizer.
#     DROPOUT (float): Dropout probability 
#     CLIP (float): Gradient clipping threshold to stabilize training.
#     OPTIMIZER (str): Choice of optimizer, either 'SGD' or 'Adam'.
#     DEVICE (torch.device): Device on which to perform training (CPU or GPU).
#     LABEL (str, optional): Identifier for the experiment run. Default is "exp".
#
# Behavior:
#     - Loads and tokenizes the Penn Treebank dataset.
#     - Constructs dataloaders for training, validation, and testing.
#     - Initializes and trains a language model with early stopping.
#     - Saves the best model and logs its performance.
#     - Plots training curves for loss and perplexity over epochs.
#     - Evaluates final model on test data and records performance metrics.
#
# Output:
#     - Saves the best model to disk.
#     - Outputs training progress to console.
#     - Saves training visualization plots.
#     - Logs final test evaluation metrics via `save_experiment_results`.
# ------------------------------------------------------------------------------
def train_model(
    train_dataset, 
    dev_dataset,
    test_dataset,
    lang,
    BATCH_SIZE,
    HID_SIZE,
    EMB_SIZE,
    N_LAYERS,
    LR,
    DROPOUT,
    CLIP,
    OPTIMIZER,
    DEVICE,
    LABEL="exp"
):
    print("HYPERPARAMETERS:")
    print("\tBatch size: ", BATCH_SIZE)
    print("\tHidden size: ", HID_SIZE)  
    print("\tEmbedding size: ", EMB_SIZE)
    print("\tNumber of layers: ", N_LAYERS)
    print("\tLearning rate: ", LR)
    print("\tDropout: ", DROPOUT)
    print("\tOptimizer: ", OPTIMIZER)
    print("\tGradient clipping: ", CLIP)

    # --------------------------------------------- DATASET MANAGEMENT ----------------------------------------------
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE,  collate_fn=partial(collate_fn, pad_token=lang.word2id["<pad>"], DEVICE=DEVICE),  shuffle=True)
    dev_loader   = DataLoader(dev_dataset,   batch_size=BATCH_SIZE*2, collate_fn=partial(collate_fn, pad_token=lang.word2id["<pad>"], DEVICE=DEVICE))
    test_loader  = DataLoader(test_dataset,  batch_size=BATCH_SIZE*2, collate_fn=partial(collate_fn, pad_token=lang.word2id["<pad>"], DEVICE=DEVICE))

    print("\tNumber of batches in train_loader:", len(train_loader))
    print("\tNumber of batches in dev_loader:", len(dev_loader))
    print("\tNumber of batches in test_loader:", len(test_loader))

    # --------------------------------------------- MODEL MANAGEMENT ----------------------------------------------
    vocab_len = len(lang.word2id)
    #model = LM_LSTM_WT(EMB_SIZE, HID_SIZE, vocab_len, pad_index=lang.word2id["<pad>"]).to(DEVICE)
    model = LM_LSTM_VD(EMB_SIZE, HID_SIZE, vocab_len, dropout=DROPOUT, pad_index=lang.word2id["<pad>"]).to(DEVICE)
    model.apply(init_weights)

    if OPTIMIZER == 'SGD':
        optimizer = optim.SGD(model.parameters(), lr=LR)
    elif OPTIMIZER == 'AdamW':
        optimizer = optim.AdamW(model.parameters(), lr=LR)

    criterion_train = nn.CrossEntropyLoss(ignore_index=lang.word2id["<pad>"])
    criterion_eval = nn.CrossEntropyLoss(ignore_index=lang.word2id["<pad>"], reduction='sum')

    n_epochs = 100
    last_epoch = 0
    patience = 3
    losses_train = []
    losses_dev = []
    ppl_list_dev = []
    sampled_epochs = []
    best_ppl = math.inf
    best_model = None
    pbar = tqdm(range(1,n_epochs))

    for epoch in pbar:
        loss = train_loop(train_loader, optimizer, criterion_train, model, CLIP)    
        if epoch % 1 == 0:
            last_epoch += 1 
            sampled_epochs.append(epoch)
            losses_train.append(np.asarray(loss).mean())
            ppl_dev, loss_dev = eval_loop(dev_loader, criterion_eval, model)

            losses_dev.append(np.asarray(loss_dev).mean())
            ppl_list_dev.append(ppl_dev)

            pbar.set_description("PPL: %f" % ppl_dev)

            if  ppl_dev < best_ppl:
                best_ppl = ppl_dev
                best_model = copy.deepcopy(model).to('cpu')
                patience = 3
            else:
                patience -= 1
                
            if patience <= 0:
                print(" Early stopping at epoch ", last_epoch, " \n\tBest PPL: ", best_ppl, "\n\tLast PPL:", ppl_list_dev[-3:])
                break

    best_model.to(DEVICE)

    # --------------------------------------------- POST TRAINING -----------------------------------------
    path = path_define(LABEL, LR, BATCH_SIZE, HID_SIZE, EMB_SIZE, N_LAYERS, DROPOUT, OPTIMIZER)
    save_model(best_model, path)

    try: 
        plot_training_progress(sampled_epochs, losses_train, losses_dev, ppl_list_dev, path)
        #plot_training_progress_wnl(sampled_epochs, losses_train, losses_dev, ppl_list_dev, path)
    except Exception as e:
        print(f"An error occurred while plotting: {e}")

    final_ppl, final_loss, sem_loss, ci_loss, sem_ppl, ci_ppl = test_eval_loop(test_loader, criterion_eval, best_model)    
    print('Test ppl: ', final_ppl)

    save_experiment_results(LABEL ,LR, N_LAYERS, BATCH_SIZE, HID_SIZE, EMB_SIZE, DROPOUT, OPTIMIZER, last_epoch, final_ppl, final_loss, sem_loss, ci_loss, sem_ppl, ci_ppl)



# ------------------------------------------------------------------------------
# Function: train_model_nt_avsgd
#
# Description:
#     Implements the Non-monotonically Triggered Averaged Stochastic Gradient Descent (NT-AvSGD) algorithm.
#     This function trains a language model using the Penn Treebank dataset with
#    specified hyperparameters. It handles the full pipeline from data preprocessing,
#    model initialization, training loop with NT-AvSGD, and evaluation.
#     Also manages logging, saving the best-performing model, and visualizing
#    training metrics such as loss and perplexity.
# 
# Parameters:
#     train_dataset (Dataset): Training dataset containing tokenized sentences.
#     dev_dataset (Dataset): Validation dataset containing tokenized sentences.
#     test_dataset (Dataset): Test dataset for final evaluation of the model.
#     lang (Lang): Language object containing vocabulary mapping (word2id, id2word).
#     BATCH_SIZE (int): Number of samples per training batch.
#     HID_SIZE (int): Size of the RNN hidden layers.
#     EMB_SIZE (int): Dimensionality of word embeddings.
#     N_LAYERS (int): Number of layers in the model.
#     LR (float): Learning rate used by the optimizer.
#     DROPOUT (float): Dropout probability
#     CLIP (float): Gradient clipping threshold to stabilize training.
#     DEVICE (torch.device): Device on which to perform training (CPU or GPU).
#     LOGGING_INTERVAL (int): Interval for logging validation perplexity.
#     LABEL (str, optional): Identifier for the experiment run. Default is "NTAvSGD".
#     NON_MONO_INTERVAL (int, optional): Non-monotone interval for NT-AvSGD. Default is 5.
# 
# Output:
#     - Saves the best model to disk.
#     - Outputs training progress to console.
#     - Saves training visualization plots.
#     - Logs final test evaluation metrics via `save_experiment_results`.
# ------------------------------------------------------------------------------
def train_model_nt_avsgd(
    train_dataset, 
    dev_dataset,
    test_dataset,
    lang,
    BATCH_SIZE,
    HID_SIZE,
    EMB_SIZE,
    N_LAYERS,
    LR,
    DROPOUT,
    CLIP,
    DEVICE,
    LABEL="NTAvSGD",
    NON_MONO_INTERVAL=5,
    LOGGING_INTERVAL=None,
):
    
    """
    Implements Non-monotonically Triggered AvSGD (NT-AvSGD) Algorithm.
        Inputs: Initial point w0, learning rate γ, logging interval L, non-monotone interval n.
         1: Initialize 
                k ← 0,      iteration count
                t ← 0,      count of validation measure ( perplexity )
                T ← 0,      flag to indicate if averaging is triggered
                logs ← []   list to store validation measure values
         2: while stopping criterion not met do
         3:     Compute stochastic gradient ∇f(wt) and take SGD step.
         4:     if mod(k, L) = 0 and T = 0 then
         5:         Compute validation perplexity v.
         6:         if t > n and v > min logs[l] then
         7:             Set T ← k
         8:         Append v to logs
         9:         t ← t + 1  
        10:     k ← k + 1
        11: end while
        return sum(wi)/(k-T+1)
    """

    # Data loaders
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE,  collate_fn=partial(collate_fn, pad_token=lang.word2id["<pad>"], DEVICE=DEVICE), shuffle=True)
    dev_loader   = DataLoader(dev_dataset,   batch_size=BATCH_SIZE*2, collate_fn=partial(collate_fn, pad_token=lang.word2id["<pad>"], DEVICE=DEVICE))
    test_loader  = DataLoader(test_dataset,  batch_size=BATCH_SIZE*2, collate_fn=partial(collate_fn, pad_token=lang.word2id["<pad>"], DEVICE=DEVICE))

    # The paper suggests that the logging interval L should be the number of iterations in an epoch  .
    if LOGGING_INTERVAL is None:
        LOGGING_INTERVAL = len(train_loader)

    print("HYPERPARAMETERS:")
    print("\tBatch size: ", BATCH_SIZE)
    print("\tHidden size: ", HID_SIZE)  
    print("\tEmbedding size: ", EMB_SIZE)
    print("\tNumber of layers: ", N_LAYERS)
    print("\tLearning rate: ", LR)
    print("\tDropout: ", DROPOUT)
    print("\tGradient clipping: ", CLIP)
    print("\tLogging interval: ", LOGGING_INTERVAL)
    print("\tNon-monotone interval: ", NON_MONO_INTERVAL)


    # Model initialization
    vocab_len = len(lang.word2id)
    model = LM_LSTM_VD(EMB_SIZE, HID_SIZE, vocab_len, dropout=DROPOUT, pad_index=lang.word2id["<pad>"]).to(DEVICE)
    model.apply(init_weights)
    model.train()  

    criterion_train = nn.CrossEntropyLoss(ignore_index=lang.word2id["<pad>"])
    criterion_eval = nn.CrossEntropyLoss(ignore_index=lang.word2id["<pad>"], reduction='sum')

    # NT-AvSGD state
    # Line 1: Initialize k ← 0, t ← 0, T ← 0, logs ← []
    k = 0
    t = 0
    T = 0
    logs = []
    
    averaged_params = None
    averaging_steps = 0
    best_ppl = math.inf
    patience = 3
    n_epochs = 100

    sampled_epochs = []
    losses_train = []
    losses_dev = []
    ppl_list_dev = []
    pbar = tqdm(range(1, n_epochs))

    for epoch in pbar:
        running_loss = 0.0
        for batch in train_loader:

            # Line 3: Compute stochastic gradient ∇ˆf(wk) and take SGD step
            # 3.1: Compute gradients
            model.zero_grad()
            input_tensor = batch["source"]
            target_tensor = batch["target"]
            output = model(input_tensor).permute(0,2,1)
            output_reshaped = output.reshape(-1, output.size(-1))   # Reshape output to [B*T, V]
            target_reshaped = target_tensor.reshape(-1)              # Flatten target to [B*T]
            #print("Output shape:", output_reshaped.shape)
            #print("Target shape:", target_reshaped.shape)
            loss = criterion_train(output_reshaped, target_reshaped)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), CLIP)

            # 3.2: Update parameters
            for param in model.parameters():
                if param.grad is not None:
                    param.data -= LR * param.grad.data

            running_loss += loss.item()

            # Line 4: if mod(k, L) = 0 and T = 0 then
            # So we compute the validation perplexity evry L iterations only if we not activate 
            # the averaging ( T = 0 )
            if k % LOGGING_INTERVAL == 0 and T == 0:

                # 5: Compute validation perplexity v.
                ppl, _ = eval_loop(dev_loader, criterion_eval, model)
                model.train()
                # 6: if t > n and v > min logs[l] then
                # If you have already made at least n previous evaluations, t > non_monotone_interval
                # and the current perplexity is worse than the minimum of the last t−n previous measurements,
                # then consider that the model is no longer improving.
                if t > NON_MONO_INTERVAL and ppl > min(logs[t - NON_MONO_INTERVAL:t]):

                    # Line 7: Set T ← k
                    T = k                                                           # Activate the averaging
                    averaged_params = [p.data.clone() for p in model.parameters()]  # Start to accumulate weights for averaging
                    averaging_steps = 1                                             # Initialize the number of iterations for averaging
                    print(f"Triggering averaging at iteration {k} with PPL: {ppl:.2f}")

                # 8: Append v to logs  
                logs.append(ppl)

                # 9: t ← t + 1
                t += 1

            elif T > 0:
                # Update running average of parameters
                for i, param in enumerate(model.parameters()):
                    averaged_params[i].add_(param.data)
                averaging_steps += 1
            
            # Line 10: k ← k + 1
            k += 1

        # Epoch-end evaluation
        sampled_epochs.append(epoch)
        avg_loss = running_loss / len(train_loader)
        losses_train.append(avg_loss)

        ppl_dev, loss_dev = eval_loop(dev_loader, criterion_eval, model)
        model.train()
        losses_dev.append(loss_dev)
        ppl_list_dev.append(ppl_dev)

        pbar.set_description(f"Epoch {epoch} | PPL: {ppl_dev:.2f}")

        
        if ppl_dev < best_ppl:
            best_ppl = ppl_dev
            patience = 3
        else:
            if T > 0:          # Decrease only after averaging
                patience -= 1  
            

        if patience <= 0:
            print(f"Early stopping at epoch {epoch}. Best PPL: {best_ppl}")
            break
        

    # Final parameter averaging
    if T > 0:
        print(f"Averaging from iteration {T} to {k} over {averaging_steps} steps.")
        with torch.no_grad():
            for i, param in enumerate(model.parameters()):
                param.data.copy_(averaged_params[i] / averaging_steps)

    # ------------------ POST-TRAINING ------------------
    model.eval()
    path = path_define(LABEL, LR, BATCH_SIZE, HID_SIZE, EMB_SIZE, N_LAYERS, DROPOUT, "NTAvSGD")
    save_model(model, path)

    try:
        plot_training_progress(sampled_epochs, losses_train, losses_dev, ppl_list_dev, path)
    except Exception as e:
        print(f"Plotting error: {e}")

    final_ppl, final_loss, sem_loss, ci_loss, sem_ppl, ci_ppl = test_eval_loop(test_loader, criterion_eval, model)
    print(f"Final test PPL: {final_ppl}")

    save_experiment_results(LABEL, LR, N_LAYERS, BATCH_SIZE, HID_SIZE, EMB_SIZE, DROPOUT, "NTAvSGD",
                            epoch, final_ppl, final_loss, sem_loss, ci_loss, sem_ppl, ci_ppl)
