# AUTOGENERATED! DO NOT EDIT! File to edit: ../../nbs/03a_recurrent.model.ipynb.

# %% auto 0
__all__ = ['Select', 'SimpleRNN', 'LSTM', 'ICLSTM', 'IclstmCB']

# %% ../../nbs/03a_recurrent.model.ipynb 3
from ..basics import *

# %% ../../nbs/03a_recurrent.model.ipynb 5
class Select(nn.Module):
    def __init__(self, idx=0):
        super().__init__()
        self.idx = idx
    def forward(self, x):
        return x[self.idx]

# %% ../../nbs/03a_recurrent.model.ipynb 7
from ..init import default_init, lambda_init

# %% ../../nbs/03a_recurrent.model.ipynb 8
class SimpleRNN(nn.Module):
    "A RNN with its output mapped through a dense layer."
    def __init__(self, ni, nh, no, num_layers=2,
                 actn='tanh',   # nonlinearity, ['tanh', 'relu']
                 init='normal', # initialization method ['uniform', 'normal', 'irnn', 'np-rnn']
                ):
        super().__init__()
        self.recurrent = nn.RNN(ni, nh, num_layers=num_layers, batch_first=True, nonlinearity=actn)
        self.dense = nn.Linear(nh, no)
        # Initialize
        self._init(self.recurrent, nh, init)
        default_init(self.dense)

    @staticmethod
    @torch.no_grad()
    def _init(m, nh, init):
        for n,p in m.named_parameters():
            if 'bias' in n:
                nn.init.zeros_(p)
            if 'weight_ih' in n:
                if init == 'uniform':
                    nn.init.uniform_(p, a=-1/np.sqrt(nh), b=1/np.sqrt(nh))
                elif init == 'np-rnn':
                    nn.init.normal_(p, std=1/np.sqrt(nh))
                    p = p * (np.sqrt(2) * np.exp(1.2 / (max(nh, 6) - 2.4)))
                    getattr(m, n).copy_(p)
                else:
                    nn.init.normal_(p, std=1/np.sqrt(nh))
            if 'weight_hh' in n:
                if init == 'uniform':
                    nn.init.uniform_(p, a=-1/np.sqrt(nh), b=1/np.sqrt(nh))
                elif init == 'irnn':
                    nn.init.eye_(p)
                elif init == 'np-rnn':
                    nn.init.normal_(p)
                    p = (p.T @ p) / nh
                    p = p / np.linalg.eigvals(p.detach().numpy()).max()
                    getattr(m, n).copy_(p)
                else:
                    nn.init.normal_(p, std=1/np.sqrt(nh))
    
    def forward(self, x):
        outp,_ = self.recurrent(x) # shape(N, L, nh)
        return self.dense(outp)

# %% ../../nbs/03a_recurrent.model.ipynb 9
class LSTM(nn.Module):
    """Custom LSTM, allowing for different activations. Assuming `batch_first=True` and `bidirectional=False`.
    
    Inputs: x, h0_c0
        x: shape (N, L, input_size)
        h0_c0: optional, default zeros, shape (num_layers, N, hidden_size)
    
    Outputs: output, (hn, cn)
        output: shape (N, L, hidden_size), outputs of the last layer for each token.
        hn: shape (N, num_layers, hidden_size), final hidden state.
        cn: shape (N, num_layers, hidden_size), final cell state.
    
    """
    def __init__(self, ni, nh, num_layers=1, actn='tanh', gate_actn='sigmoid',
                 dropout=0.0, unit_forget_bias=True, init_gain=1/np.sqrt(3), recurrent_init_gain=1.):
        super().__init__()
        self.nh,self.num_layers = nh,num_layers
        self.actn = getattr(F, actn, 'tanh')
        self.gate_actn = getattr(F, gate_actn, 'sigmoid')
        self.dropout = nn.Dropout(p=dropout)

        ws = []
        for i in range(num_layers):
            ws.append(nn.ModuleDict({
                'ii': nn.Linear(ni if i == 0 else nh, nh),  # input gate
                'hi': nn.Linear(nh, nh),
                'if': nn.Linear(ni if i == 0 else nh, nh),  # forget gate
                'hf': nn.Linear(nh, nh),
                'io': nn.Linear(ni if i == 0 else nh, nh),  # output gate
                'ho': nn.Linear(nh, nh),
                'ic': nn.Linear(ni if i == 0 else nh, nh),  # cell gate
                'hc': nn.Linear(nh, nh)
            }))
        self.ws = nn.ModuleList(ws)
        
        # Initialize
        for n,p in self.named_parameters():
            # hidden/recurrent weight
            if '.h' in n:
                if 'bias' in n:
                    nn.init.zeros_(p)
                else:
                    nn.init.orthogonal_(p, recurrent_init_gain)
            # non-recurrent weight
            else:
                if 'bias' in n:
                    if '.if' in n and unit_forget_bias:
                        nn.init.ones_(p)
                    else:
                        nn.init.zeros_(p)
                else:
                    nn.init.xavier_uniform_(p, init_gain) 
    
    def _forward_single(self, x, h0_c0: list=None):
        "Forward pass of a single token."
        if h0_c0 is None:
            h0 = torch.zeros(self.num_layers, x.shape[0], self.nh, device=x.device)
            c0 = torch.zeros(self.num_layers, x.shape[0], self.nh, device=x.device)
        else:
            h0,c0 = h0_c0
            assert (h0.shape[-1] == c0.shape[-1] == self.nh) and (h0.shape[1] == c0.shape[1] == x.shape[0])
        
        hs, cs = [], []
        for i in range(self.num_layers):
            h, c = h0[i], c0[i]
            i_gate = self.ws[i]['ii'](x) + self.ws[i]['hi'](h)
            f_gate = self.ws[i]['if'](x) + self.ws[i]['hf'](h)
            o_gate = self.ws[i]['io'](x) + self.ws[i]['ho'](h)
            c_gate = self.ws[i]['ic'](x) + self.ws[i]['hc'](h)

            i_gate = self.gate_actn(i_gate)
            f_gate = self.gate_actn(f_gate)
            o_gate = self.gate_actn(o_gate)
            c_gate = self.actn(c_gate)

            c_new = (f_gate * c) + (i_gate * c_gate)
            h_new = o_gate * self.actn(c_new)
            cs.append(c_new)
            hs.append(h_new)
            x = self.dropout(h_new)

        hs, cs = torch.stack(hs, 0), torch.stack(cs, 0)
        return (hs, cs)

    def forward(self, x, h0_c0=None):
        # Input `x`, shape (N,L,D); `h0_c0`, shape (num_layers, N, nh).
        hs = []
        cs = []
        for xi in torch.permute(x, [1,0,2]):
            hc = self._forward_single(xi, h0_c0)
            hs.append(hc[0])
            cs.append(hc[1])
            h0_c0 = hc
        output = torch.stack([h[-1] for h in hs], 1)
        return output, (hs[-1], cs[-1])

# %% ../../nbs/03a_recurrent.model.ipynb 11
class ICLSTM(nn.Module):
    """Input convex LSTM. From https://arxiv.org/abs/2311.07202.
    A L-ICLSTM is a stack of [LSTM, Linear, ReLU] repeated L times. The output is mapped through another Linear layer.
    For it to be input convex, all weights are constrained to be non-negative, 
    and all activations are convex, non-decreasing and non-negative (no activation is applied to the output in the code.)
    """
    def __init__(self, ni, nh, no, num_layers=2, expand_inp=True, actn='relu', gate_actn='relu', **kwargs):
        super().__init__()
        ni = ni * 2 if expand_inp else ni
        self.expand_inp = expand_inp
        self.actn = getattr(F, actn, 'relu')
        self.blocks = nn.ModuleList([self._mk_block(ni, nh, actn, gate_actn, **kwargs) for _ in range(num_layers)])
        self.dense_out = nn.Linear(ni, no)
        # Nonnegative weights
        self.weight_constraint()

    def _mk_block(self, ni, nh, actn, gate_actn, **kwargs):
        m = nn.Sequential(LSTM(ni, nh, 1, actn=actn, gate_actn=gate_actn, **kwargs),
                          Select(), nn.Linear(nh, ni))
        default_init(m[2], normal=False)
        return m
        
    def weight_constraint(self):
        "Apply nonnegative weight constriant."
        with torch.no_grad():
            for n,p in self.named_parameters():
                if 'weight' in n:
                    p.clamp_min_(0)

    def forward(self, x):
        if self.expand_inp: x = torch.cat([x, -x], dim=-1)
        x0 = x.clone()
        for b in self.blocks:
            x = self.actn(b(x)) + x0
        return self.dense_out(x)

# %% ../../nbs/03a_recurrent.model.ipynb 12
class IclstmCB(Callback):
    order = 10
    "ICLSTM training callback, to ensure updated weights are nonnegative."
    def after_step(self): self.learner.model.weight_constraint()
