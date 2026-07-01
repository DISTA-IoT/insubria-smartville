import torch
import torch.nn as nn
import torch.nn.functional as F

"""
CONFIDENCE_DECODER_CLASS_NAME = 'ConfidenceDecoder'
KERNEL_REGRESSION_LOSS_CLASS_NAME = 'KernelRegressionLoss'
ONE_STREAM_MULTICLASS_FLOW_CLASSIFIER_CLASS_NAME = 'OneStreamMulticlassFlowClassifier'
TWO_STREAM_MULTICLASS_FLOW_CLASSIFIER_CLASS_NAME = 'TwoStreamMulticlassFlowClassifier'
THREE_STREAM_MULTICLASS_FLOW_CLASSIFIER_CLASS_NAME = 'ThreeStreamMulticlassFlowClassifier'

This model file is identical to optim.py EXCEPT for ConfidenceDecoder, which
scores anomalies (zero-days) by the *relative Mahalanobis distance* to the
known-class Gaussians instead of the nearest-centroid inverse-Euclidean
distance. See the ConfidenceDecoder docstring for the why and the math.
"""
torch.set_flush_denormal(True) # Fixes potential micro-float CPU slowdown
torch.set_num_threads(4)       # Stops possible thread traffic jams


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

        out, _ = self.gru(x, None)
        return F.relu(out[:, -1, :])


class ConfidenceDecoder(nn.Module):
    """
    Relational anomaly (zero-day) scorer based on the *relative Mahalanobis
    distance* (RMD, Ren et al. 2021) to the known-class Gaussians, replacing
    the previous nearest-centroid inverse-Euclidean score
    (`sigmoid(1 - max_k sim_k)`).

    Why: the old score treated every direction in hidden space as equally
    surprising -- it measured plain Euclidean distance to each class *mean* and
    took the nearest. So a real zero-day that happens to land near a known
    class's mean, but off that class's actual manifold (e.g. displaced along a
    direction in which the class has almost no spread), scored as
    non-anomalous and was missed. Mahalanobis distance whitens by each class's
    own covariance, so "near the mean" stops implying "in-distribution": a
    displacement along a tight direction now costs a lot, along a wide
    direction little. The *relative* variant additionally subtracts a
    class-agnostic background Gaussian, which is what makes it strong in the
    near-OOD regime (a novelty sitting close to a known class).

    Relational bottleneck preserved: the head still sees ONLY the query point's
    relation to the known classes (its Mahalanobis distances to the known
    Gaussians), never absolute coordinates -- we've only upgraded the metric
    from isotropic-Euclidean-to-mean to covariance-aware-to-distribution.

    Parameter-free and self-calibrating: min_k RMD_k is naturally centred at
    zero (negative when the point fits some known class better than the shared
    background, i.e. in-distribution; >= 0 for a novelty), so no learnable
    scale is needed and the RMD=0 decision boundary maps to probability 0.5.
    Being parameter-free also means (a) the AD/BCE loss keeps shaping the
    *encoder's* geometry, backpropagating through the distances exactly as
    before, and (b) an (empty) pretrained confidence-decoder checkpoint still
    loads.

    Covariance is estimated *tied* (one shared diagonal covariance pooled over
    all known-class support residuals) and *diagonal*, with shrinkage toward
    the mean variance and a floor -- the sample-efficient, always-invertible
    choice given k-shot support in a high-dimensional hidden space (per-class
    full covariance is not estimable from a handful of support points).

    Output: a per-query anomaly probability in (0, 1), shape [n_query, 1] --
    the same contract the rest of the pipeline expects from this module (the
    `> 0.5` routing threshold and the confidence-strategy readouts all treat
    it as a probability), so it is a drop-in replacement.
    """

    def __init__(self, device):
        super(ConfidenceDecoder, self).__init__()
        self.device = device
        # Numerical floor on per-dimension variances (keeps the diagonal
        # covariance strictly positive / invertible).
        self.var_floor = 1e-4
        # James-Stein-style shrinkage of the diagonal covariance toward its own
        # mean variance -- stabilises the estimate when support is scarce.
        self.shrinkage = 0.1

    def _diag_cov(self, second_moment):
        """Shrink toward the mean variance, then floor."""
        v = (1.0 - self.shrinkage) * second_moment + self.shrinkage * second_moment.mean()
        return v.clamp_min(self.var_floor)

    def forward(self, hidden_vectors, labels, query_mask, known_class_mask, **kwargs):
        query_mask = query_mask.view(-1).bool()
        support_mask = ~query_mask
        support_h = hidden_vectors[support_mask]                 # [S, D]
        support_y = labels.view(-1).long()[support_mask]         # [S]
        query_h = hidden_vectors[query_mask]                     # [Q, D]
        Q, D = query_h.shape

        known_ids = known_class_mask.view(-1).nonzero(as_tuple=False).view(-1).tolist()

        # Per-known-class centroids from support; keep only classes that
        # actually have support samples this batch, and collect their
        # within-class residuals for the tied covariance.
        centroids = []
        residual_chunks = []
        known_support_chunks = []
        for k in known_ids:
            m = support_y == k
            if m.any():
                ch = support_h[m]
                mu_k = ch.mean(dim=0)
                centroids.append(mu_k)
                residual_chunks.append(ch - mu_k)
                known_support_chunks.append(ch)

        # Degenerate: nothing to model the known distribution with -> abstain
        # (probability 0.5, i.e. not routed as anomalous under the > 0.5 test).
        if len(centroids) == 0:
            return torch.full((Q, 1), 0.5, device=hidden_vectors.device, dtype=query_h.dtype)

        centroids = torch.stack(centroids, dim=0)                # [Kv, D]
        residuals = torch.cat(residual_chunks, dim=0)            # [Sk, D]
        known_support = torch.cat(known_support_chunks, dim=0)   # [Sk, D]

        # Tied within-class diagonal covariance (pooled second moment of the
        # residuals, which have ~zero mean by construction).
        within_var = self._diag_cov(residuals.pow(2).mean(dim=0))            # [D]
        # Class-agnostic background diagonal Gaussian over the known support.
        mu0 = known_support.mean(dim=0)                                       # [D]
        var0 = self._diag_cov(((known_support - mu0) ** 2).mean(dim=0))       # [D]

        # Diagonal Mahalanobis^2 from each query point to each known centroid
        # and to the background.
        diff = query_h.unsqueeze(1) - centroids.unsqueeze(0)                  # [Q, Kv, D]
        m_k = (diff * diff / within_var.view(1, 1, -1)).sum(dim=-1)           # [Q, Kv]
        diff0 = query_h - mu0.unsqueeze(0)                                    # [Q, D]
        m0 = (diff0 * diff0 / var0.view(1, -1)).sum(dim=-1)                   # [Q]

        # Relative Mahalanobis distance and the nearest-class reduction.
        rmd = m_k - m0.unsqueeze(1)                                           # [Q, Kv]
        min_rmd = rmd.min(dim=1).values                                       # [Q]

        # Per-dimension normalisation keeps the sigmoid in a trainable range
        # while preserving the natural RMD=0 -> prob 0.5 decision boundary
        # (< 0.5 in-distribution, > 0.5 novelty).
        z = min_rmd / float(D)
        return torch.sigmoid(z).unsqueeze(-1)                                 # [Q, 1]


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
        repulsive = -(1.0 - baseline_kernel) * torch.log(1.0 - predicted_kernel + 1e-10)
        attractive = -(baseline_kernel * torch.log(predicted_kernel + 1e-10))
        # preserve the original reduction: sum rows, then mean over rows
        return (self.r_w * repulsive + self.a_w * attractive).sum(dim=1).mean()


class SimmilarityNet(nn.Module):
    def __init__(
            self,
            hidden_size):
        super(SimmilarityNet, self).__init__()

        self.act = nn.LeakyReLU(0.2)
        self.fc1 = nn.Linear(hidden_size, hidden_size // 2)
        self.fc2 = nn.Linear(hidden_size // 2, 1)

    def forward(self, x1, x2):
        input_to_symm = torch.abs(x1 - x2)
        symm = self.fc1(input_to_symm)
        symm = self.act(symm)
        symm = self.fc2(symm)
        return symm



class DistKernelRegressor(nn.Module):
    """
    Optimized Distance-based Kernel Regressor.
    Computes only the upper triangle of the similarity matrix to save ~50% CPU.
    """
    def __init__(self, kwargs):
        super(DistKernelRegressor, self).__init__()
        self.device = kwargs.get('device', 'cpu')
        in_features = int(kwargs.get('in_features', 128))

        sim_net = SimmilarityNet(hidden_size=in_features)

        self.similarity_network = sim_net

    def forward(self, hiddens):
        n = hiddens.shape[0]
        if n <= 1:
            return hiddens, torch.ones((n, n), device=hiddens.device)

        # 1. Get indices for the upper triangle (i < j)
        indices = torch.triu_indices(n, n, offset=1, device=hiddens.device)

        # 2. Extract unique pairs
        h1 = hiddens[indices[0]]
        h2 = hiddens[indices[1]]

        # 3. Compute similarity for all unique pairs in one batch
        upper_tri_energies = self.similarity_network(h1, h2)
        upper_tri_sim = torch.sigmoid(upper_tri_energies).squeeze(-1)

        # 4. Fill symmetric matrix
        # Self-similarity (diagonal) is 1.0
        kernel = torch.eye(n, device=hiddens.device)
        kernel[indices[0], indices[1]] = upper_tri_sim
        kernel[indices[1], indices[0]] = upper_tri_sim

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
        flow_input_size = int(kwargs['first_stream_input_size'])
        self.flow_normalizer = nn.BatchNorm1d(flow_input_size)
        self.use_encoder = kwargs['use_encoder']
        flow_rnn_input_dim = flow_input_size
        second_stream_input_size = second_stream_rnn_input_dim = int(kwargs['second_stream_input_size'])
        third_stream_input_size = third_stream_rnn_input_dim = int(kwargs['third_stream_input_size'])
        hidden_size = int(kwargs['hidden_size'])
        dropout_prob = float(kwargs['dropout'])
        if self.use_encoder:
            flow_rnn_input_dim = hidden_size
            second_stream_rnn_input_dim = hidden_size
            third_stream_rnn_input_dim = hidden_size
            self.flow_encoder = MLP(flow_input_size, hidden_size, dropout_prob)
            self.second_stream_encoder = MLP(second_stream_input_size, hidden_size, dropout_prob)
            self.third_stream_encoder = MLP(third_stream_input_size, hidden_size, dropout_prob)

        self.flow_rnn = RecurrentModel(flow_rnn_input_dim, hidden_size, dropout_prob, int(kwargs['recurrent_layers']), device=self.device)
        self.second_stream_normalizer = nn.BatchNorm1d(second_stream_input_size)
        self.second_stream_rnn = RecurrentModel(second_stream_rnn_input_dim, hidden_size, dropout_prob, int(kwargs['recurrent_layers']), device=self.device)
        self.third_stream_normalizer = nn.BatchNorm1d(third_stream_input_size)
        self.third_stream_rnn = RecurrentModel(third_stream_rnn_input_dim, hidden_size, dropout_prob, int(kwargs['recurrent_layers']), device=self.device)
        self.kernel_regressor = DistKernelRegressor(
            {'device': self.device,
            'dropout': dropout_prob,
            'n_heads': int(kwargs['kernel_regressor_heads']),
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
    def __init__(self, kwargs):
        super(TwoStreamMulticlassFlowClassifier, self).__init__()
        self.device = kwargs['device']
        flow_input_size = int(kwargs['first_stream_input_size'])
        self.flow_normalizer = nn.BatchNorm1d(flow_input_size)
        flow_rnn_input_dim = flow_input_size
        second_stream_input_size = second_stream_rnn_input_dim = int(kwargs['second_stream_input_size'])
        hidden_size = int(kwargs['hidden_size'])
        dropout_prob = float(kwargs['dropout'])
        self.use_encoder = kwargs['use_encoder']
        if self.use_encoder:
            flow_rnn_input_dim = hidden_size
            second_stream_rnn_input_dim = hidden_size
            self.flow_encoder = MLP(flow_input_size, hidden_size, dropout_prob)
            self.second_stream_encoder = MLP(second_stream_input_size, hidden_size, dropout_prob)

        self.flow_rnn = RecurrentModel(flow_rnn_input_dim, hidden_size, dropout_prob, int(kwargs['recurrent_layers']), device=self.device)
        self.second_stream_normalizer = nn.BatchNorm1d(second_stream_input_size)
        self.second_stream_rnn = RecurrentModel(second_stream_rnn_input_dim, hidden_size, dropout_prob, int(kwargs['recurrent_layers']), device=self.device)
        self.kernel_regressor = DistKernelRegressor(
            {'device': self.device,
            'dropout': dropout_prob,
            'n_heads': int(kwargs['kernel_regressor_heads']),
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


class OneStreamMulticlassFlowClassifier(nn.Module):
    def __init__(self, kwargs=None):
        super(OneStreamMulticlassFlowClassifier, self).__init__()
        self.device=kwargs['device']
        rnn_input_dim = input_size = int(kwargs['first_stream_input_size'])
        self.normalizer = nn.BatchNorm1d(input_size)
        hidden_size = int(kwargs['hidden_size'])
        dropout_prob = float(kwargs['dropout'])
        self.use_encoder = kwargs['use_encoder']
        if self.use_encoder:
            rnn_input_dim = hidden_size
            self.encoder = MLP(input_size, hidden_size, dropout_prob)
        self.rnn = RecurrentModel(rnn_input_dim, hidden_size, dropout_prob, int(kwargs['recurrent_layers']), device=self.device)
        self.kernel_regressor = DistKernelRegressor(
            {'device': self.device,
            'dropout': dropout_prob,
            'n_heads': int(kwargs['kernel_regressor_heads']),
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
