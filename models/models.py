import torch
import torch.nn as nn
import torch.nn.functional as F

"""
CONFIDENCE_DECODER_CLASS_NAME = 'ConfidenceDecoder'
KERNEL_REGRESSION_LOSS_CLASS_NAME = 'KernelRegressionLoss'
ONE_STREAM_MULTICLASS_FLOW_CLASSIFIER_CLASS_NAME = 'OneStreamMulticlassFlowClassifier'
TWO_STREAM_MULTICLASS_FLOW_CLASSIFIER_CLASS_NAME = 'TwoStreamMulticlassFlowClassifier'
THREE_STREAM_MULTICLASS_FLOW_CLASSIFIER_CLASS_NAME = 'ThreeStreamMulticlassFlowClassifier'
"""


class MLP(nn.Module):
    def __init__(self, input_size, output_size, dropout):
        super(MLP, self).__init__()
        hidden_size = (output_size - input_size) // 2
        hidden_size = output_size - hidden_size
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(hidden_size, output_size)
        self.act = nn.LeakyReLU(0.2)
    def forward(self, x):
        x = self.act(self.fc1(x))
        x = self.dropout(x)
        return self.fc2(x)
    

class RecurrentModel(nn.Module):

    def __init__(self, input_size, hidden_size, dropout, recurrent_layers, device='cpu'):
        super(RecurrentModel, self).__init__()
        self.device = device
        self.hidden_size = hidden_size
        self.gru = nn.GRU(input_size, hidden_size, dropout=dropout, num_layers=int(recurrent_layers), batch_first=True)

    def forward(self, x):
        # Initialize hidden state
        h0 = torch.zeros(self.gru.num_layers, x.size(0), self.hidden_size).to(x.device)
        
        # Forward pass through GRU layer
        out, _ = self.gru(x, h0)
        
        return F.relu(out[:, -1, :])
    

class ConfidenceDecoder(nn.Module):

    def __init__(
            self,
            device):

        super(ConfidenceDecoder, self).__init__()
        self.device = device


    def forward(
            self,
            scores):

        scores = (1 - scores.unsqueeze(-1)).min(1)[0]

        unknown_indicators = torch.sigmoid(scores)
        return unknown_indicators
    

class KernelRegressionLoss(nn.Module):

    def __init__(
            self,
            repulsive_weigth: int = 1, 
            attractive_weigth: int = 1,
            device: str = "cpu"):
        super(KernelRegressionLoss, self).__init__()
        self.r_w = repulsive_weigth
        self.a_w = attractive_weigth
        self.device = device

    def forward(self, baseline_kernel, predicted_kernel):
        # REPULSIVE force
        repulsive_CE_term = -(1 - baseline_kernel) * torch.log(1-predicted_kernel + 1e-10)
        repulsive_CE_term = repulsive_CE_term.sum(dim=1)
        repulsive_CE_term = repulsive_CE_term.mean()

        # The following acts as an ATTRACTIVE force for the embedding learning:
        attractive_CE_term = -(baseline_kernel * torch.log(predicted_kernel + 1e-10))
        attractive_CE_term = attractive_CE_term.sum(dim=1)
        attractive_CE_term = attractive_CE_term.mean()

        return (self.r_w * repulsive_CE_term) + (self.a_w * attractive_CE_term)
    
    
class SimmilarityNet(nn.Module):
    def __init__(
            self,
            h_dim):
        super(SimmilarityNet, self).__init__()

        self.act = nn.LeakyReLU(0.2)
        self.fc1 = nn.Linear(h_dim, h_dim // 2)
        self.fc2 = nn.Linear(h_dim // 2, 1)

    def forward(self, x1, x2):
        input_to_symm = torch.abs(x1 - x2)
        symm = self.fc1(input_to_symm)
        symm = self.act(symm)
        symm = self.fc2(symm)
        return symm



class DistKernelRegressor(nn.Module):

    def __init__(
            self,
            kwargs):

        super(DistKernelRegressor, self).__init__()

        self.device = kwargs['device']
        self.w = nn.Parameter(torch.tensor(1.0))
        self.b = nn.Parameter(torch.tensor(-0.5))
        self.similarity_network = SimmilarityNet(h_dim=kwargs['in_features'])

    def forward(
            self,
            hiddens):
        
        n_nodes = hiddens.shape[0]

        h_pivot = hiddens.repeat(
            n_nodes,
            1)

        h_interleave = hiddens.repeat_interleave(
            n_nodes,
            dim=0)
        
        energies = self.similarity_network(h_pivot, h_interleave)

        kernel = torch.sigmoid(energies)

        kernel = kernel.reshape(n_nodes,n_nodes)

        return hiddens, kernel



class DotProdKernelRegressor(nn.Module):

    def __init__(
            self,
            kwargs):

        super(DotProdKernelRegressor, self).__init__()

        self.act = nn.Sigmoid()
        self.device = kwargs['device']

    def forward(
            self,
            hiddens):
        
        kernel = self.act(hiddens @ hiddens.T)

        return hiddens, kernel


class MulticlassPrototypicalClassifier(nn.Module):

    def __init__(self, device='cpu'):
        super(MulticlassPrototypicalClassifier, self).__init__()
        self.device = device


    def get_oh_labels(
        self,
        decimal_labels,
        n_way):

        # create placeholder for one_hot encoding:
        labels_onehot = torch.zeros(
            [decimal_labels.size()[0],
            n_way], device=self.device)
        # transform to one_hot encoding:
        labels_onehot = labels_onehot.scatter(
            1,
            decimal_labels,
            1)
        return labels_onehot


    def get_centroids(
            self,
            hidden_vectors,
            onehot_labels):
        """
        Compute the centroids (cluster centers) for a set of hidden representation vectors, 
        based on their one-hot encoded class assignments. This method handles cases where 
        some clusters may not have any samples in the batch (missing clusters).
        
        Args:
        hidden_vectors (torch.Tensor): A 2D tensor of shape (N, D), where N is the number 
                                    of samples and D is the dimensionality of the hidden representations.
        onehot_labels (torch.Tensor): A 2D tensor of shape (N, K), where N is the number 
                                    of samples and K is the number of classes. Each row is 
                                    a one-hot encoded label indicating the class assignment 
                                    for each sample.
        
        Returns:
        tuple: A tuple containing:
            - centroids (torch.Tensor): A 2D tensor of shape (K, D) representing the centroids 
                                        for each class. If a class has no samples in the batch, 
                                        its centroid will remain as zeros.
            - missing_clusters (torch.Tensor): A 1D boolean tensor of length K, where True 
                                            indicates that a class is missing (i.e., has 
                                            no samples in the batch), and False means that 
                                            the class has at least one sample.
        """
        
        # Perform matrix multiplication to aggregate hidden vectors by class (onehot_labels.T @ hidden_vectors)
        # This step sums the hidden_vectors for all samples belonging to each class.
        cluster_agg = onehot_labels.T @ hidden_vectors

        # Compute the number of samples for each class by summing over the one-hot encoded labels.
        samples_per_cluster = onehot_labels.sum(0)
        
        # Initialize centroids as a zero tensor of the same shape as the aggregated hidden vectors.
        centroids = torch.zeros_like(cluster_agg, device=self.device)
        
        # Identify missing clusters, i.e., classes with zero samples.
        missing_clusters = samples_per_cluster == 0

        # For the clusters that have samples, compute the centroid by dividing the summed hidden vectors
        # by the number of samples in each cluster.
        existent_centroids = cluster_agg[~missing_clusters] / samples_per_cluster[~missing_clusters].unsqueeze(-1)
        
        # Assign the computed centroids to their corresponding positions in the centroids tensor.
        centroids[~missing_clusters] = existent_centroids

        return centroids, missing_clusters
    

    def forward(self, hidden_vectors, labels, known_attacks_count, query_mask):
        """
        known_attacks_count is the current number of known attacks. 
        """
        # get one_hot_labels of current batch:
        oh_labels = self.get_oh_labels(
            decimal_labels=labels.long(),
            n_way=known_attacks_count)

        # get latent centroids:
        centroids, _ = self.get_centroids(
            hidden_vectors[~query_mask],
            oh_labels[~query_mask])

        # compute scores:
        scores = 1 / (torch.cdist(hidden_vectors[query_mask], centroids) + 1e-10)

        return scores


class ThreeStreamMulticlassFlowClassifier(nn.Module):
    def __init__(self, kwargs):
        super(ThreeStreamMulticlassFlowClassifier, self).__init__()
        self.device = kwargs['device']
        flow_input_size = kwargs['first_stream_input_size']
        self.flow_normalizer = nn.BatchNorm1d(flow_input_size)
        self.use_encoder = False
        flow_rnn_input_dim = flow_input_size
        second_stream_input_size = second_stream_rnn_input_dim = kwargs['second_stream_input_size']
        third_stream_input_size = third_stream_rnn_input_dim = kwargs['third_stream_input_size']
        hidden_size = kwargs['hidden_size']
        dropout_prob = kwargs['dropout']
        if kwargs['use_encoder']:
            self.use_encoder = True
            self.flow_rnn_input_dim = hidden_size
            self.second_stream_rnn_input_dim = hidden_size
            self.third_stream_rnn_input_dim = hidden_size
            self.flow_encoder = MLP(flow_input_size, hidden_size, dropout_prob)
            self.second_stream_encoder = MLP(second_stream_input_size, hidden_size, dropout_prob)
            self.third_stream_encoder = MLP(third_stream_input_size, hidden_size, dropout_prob)

        self.flow_rnn = RecurrentModel(flow_rnn_input_dim, hidden_size, dropout_prob, kwargs['recurrent_layers'], device=self.device)
        self.second_stream_normalizer = nn.BatchNorm1d(second_stream_input_size)
        self.second_stream_rnn = RecurrentModel(second_stream_rnn_input_dim, hidden_size, dropout_prob, kwargs['recurrent_layers'], device=self.device)
        self.third_stream_normalizer = nn.BatchNorm1d(third_stream_input_size)
        self.third_stream_rnn = RecurrentModel(third_stream_rnn_input_dim, hidden_size, dropout_prob, kwargs['recurrent_layers'], device=self.device)
        self.kernel_regressor = DistKernelRegressor( # Try also DotProdKernelRegressor
            {'device': self.device,
            'dropout': dropout_prob,
            'n_heads': kwargs['kernel_regressor_heads'],
            'in_features': hidden_size*3,
            'out_features': hidden_size*3})
        self.classifier = MulticlassPrototypicalClassifier(device=self.device)

    def forward(self, flows, second_domain_feats, third_domain_feats, labels, curr_known_attack_count, query_mask):
        
        flows = self.flow_normalizer(flows.permute((0,2,1))).permute((0,2,1))
        second_domain_feats = self.second_stream_normalizer(second_domain_feats.permute((0,2,1))).permute((0,2,1))
        third_domain_feats = self.third_stream_normalizer(third_domain_feats.permute((0,2,1))).permute((0,2,1))

        if self.use_encoder:
            flows = self.flow_encoder(flows)
            second_domain_feats = self.second_stream_encoder(second_domain_feats)
            third_domain_feats = self.third_stream_encoder(third_domain_feats)

        flows = self.flow_rnn(flows)
        second_domain_feats = self.second_stream_rnn(second_domain_feats)
        third_domain_feats = self.third_stream_rnn(third_domain_feats)

        hiddens = torch.cat([flows, second_domain_feats, third_domain_feats], dim=1)

        hiddens, predicted_kernel = self.kernel_regressor(hiddens)
        logits  = self.classifier(hiddens, labels, curr_known_attack_count, query_mask)

        return logits, hiddens, predicted_kernel
 

class TwoStreamMulticlassFlowClassifier(nn.Module):
    def __init__(self, flow_input_size, second_stream_input_size, hidden_size, dropout_prob=0.2, kr_heads=8, device='cpu', kwargs=None):
        super(TwoStreamMulticlassFlowClassifier, self).__init__()
        self.device = device
        self.flow_normalizer = nn.BatchNorm1d(flow_input_size)
        flow_rnn_input_dim = flow_input_size
        second_stream_rnn_input_dim = second_stream_input_size
        self.use_encoder = False
        if kwargs['use_encoder']:
            self.use_encoder = True
            flow_rnn_input_dim = hidden_size
            second_stream_rnn_input_dim = hidden_size
            self.flow_encoder = MLP(flow_input_size, hidden_size, dropout_prob)
            self.second_stream_encoder = MLP(second_stream_input_size, hidden_size, dropout_prob)

        self.flow_rnn = RecurrentModel(flow_rnn_input_dim, hidden_size, dropout_prob, kwargs['recurrent_layers'], device=self.device)
        self.second_stream_normalizer = nn.BatchNorm1d(second_stream_input_size)
        self.second_stream_rnn = RecurrentModel(second_stream_rnn_input_dim, hidden_size, dropout_prob, kwargs['recurrent_layers'], device=self.device)
        kernel_regressor_class = DistKernelRegressor if kwargs['kr_type'] == 'dist' else DotProdKernelRegressor 
        self.kernel_regressor = kernel_regressor_class(
            {'device': self.device,
            'dropout': dropout_prob,
            'n_heads': kr_heads,
            'in_features': hidden_size*2,
            'out_features': hidden_size*2})
        self.classifier = MulticlassPrototypicalClassifier(device=self.device)

    def forward(self, flows, second_domain_feats, labels, curr_known_attack_count, query_mask):
        
        flows = self.flow_normalizer(flows.permute((0,2,1))).permute((0,2,1))
        second_domain_feats = self.second_stream_normalizer(second_domain_feats.permute((0,2,1))).permute((0,2,1))

        if self.use_encoder:
            flows = self.flow_encoder(flows)
            second_domain_feats = self.second_stream_encoder(second_domain_feats)

        flows = self.flow_rnn(flows)
        second_domain_feats = self.second_stream_rnn(second_domain_feats)

        hiddens = torch.cat([flows, second_domain_feats], dim=1)

        hiddens, predicted_kernel = self.kernel_regressor(hiddens)
        logits  = self.classifier(hiddens, labels, curr_known_attack_count, query_mask)

        return logits, hiddens, predicted_kernel
 

class OneStreamMultiClassFlowClassifier(nn.Module):
    def __init__(self, input_size, hidden_size, dropout_prob, kr_heads=8,device='cpu', kwargs=None):
        super(OneStreamMultiClassFlowClassifier, self).__init__()
        self.device=device
        self.normalizer = nn.BatchNorm1d(input_size)
        rnn_input_dim = input_size
        self.use_encoder = False
        if kwargs['use_encoder']:
            self.use_encoder = True
            rnn_input_dim = hidden_size
            self.encoder = MLP(input_size, hidden_size, dropout_prob)
        self.rnn = RecurrentModel(rnn_input_dim, hidden_size, dropout_prob, kwargs['recurrent_layers'], device=self.device)
        kernel_regressor_class = DistKernelRegressor if kwargs['kr_type'] == 'dist' else DotProdKernelRegressor            
        self.kernel_regressor = kernel_regressor_class(
            {'device': self.device,
            'dropout': dropout_prob,
            'n_heads': kr_heads,
            'in_features': hidden_size,
            'out_features': hidden_size})
        self.classifier = MulticlassPrototypicalClassifier(device=self.device)

    def forward(self, x, labels, curr_known_attack_count, query_mask):
        # nn.BatchNorm1d ingests (N,C,L), where N is the batch size, 
        # C is the number of features or channels, and L is the sequence length
        x = self.normalizer(x.permute((0,2,1))).permute((0,2,1))
        if self.use_encoder:
            x = self.encoder(x)
        hiddens = self.rnn(x)
        hiddens, predicted_kernel = self.kernel_regressor(hiddens)
        logits  = self.classifier(hiddens, labels, curr_known_attack_count, query_mask)
        return logits, hiddens, predicted_kernel

