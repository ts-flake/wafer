# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_core.ipynb.

# %% auto 0
__all__ = ['to_device', 'to_detach', 'to_cpu', 'has_children', 'has_params', 'Callback', 'DeviceCB', 'BatchXfmCB', 'MetricCB',
           'ProgressCB', 'BaseLogCB', 'ClipGradCB', 'LRCB', 'Hook', 'Hooks', 'Learner', 'Dataloader', 'mk_dls_from_ds',
           'mk_dls_from_hub', 'Scaler']

# %% ../nbs/00_core.ipynb 3
from .imports import *
from collections.abc import Mapping

# %% ../nbs/00_core.ipynb 5
def to_device(xs, device):
    if isinstance(xs, (tuple, list)): return type(xs)(x.to(device=device) for x in list(xs))
    if isinstance(xs, Mapping): return {k:v.to(device=device) for k,v in xs.items()}
    return xs.to(device=device)

def to_detach(xs):
    if isinstance(xs, (tuple, list)): return type(xs)(x.detach() for x in list(xs))
    if isinstance(xs, Mapping): return {k:v.detach() for k,v in xs.items()}
    return xs.detach()

def to_cpu(xs):
    if isinstance(xs, (tuple, list)): return type(xs)(x.cpu() for x in list(xs))
    if isinstance(xs, Mapping): return {k:v.cpu() for k,v in xs.items()}
    return xs.cpu()

# %% ../nbs/00_core.ipynb 6
def has_children(m):
    try: next(m.children())
    except StopIteration: return False
    return True

def has_params(m): return len(list(m.parameters())) > 0

# %% ../nbs/00_core.ipynb 8
class Callback(): order = -1

# %% ../nbs/00_core.ipynb 9
class DeviceCB(Callback):
    "Move the model and batch to the correct device for training."
    order = -10
    def before_fit(self): self.learner.model.to(device=self.learner.device)
    def before_batch(self): to_device(self.learner.batch, self.learner.device)

# %% ../nbs/00_core.ipynb 10
class BatchXfmCB(Callback):
    "Apply a data transform to a batch."
    order = -5
    def __init__(self, xfm): self.xfm = xfm
    def before_batch(self):
        self.learner.batch = self.xfm(self.learner.batch)

# %% ../nbs/00_core.ipynb 11
class MetricCB(Callback):
    "Using metrics from [`torcheval`](https://pytorch.org/torcheval/stable/) as callbacks."
    order = 10
    def __init__(self, metrics: tuple|list,
                 names: tuple|list[str]=None,
                 train: bool=False # Compute metrics on train set; default on test set
                ):
        if names is not None: assert len(metrics) == len(names), "sizes of `names` and `metrics` do not match."
        else: names = [type(metric).__name__ for metric in metrics]
        self.metrics,self.names,self.train = metrics,names,train
        for metric,name in zip(self.metrics, self.names): metric.name = name
    
    def reset(self):
        for metric in self.metrics: metric.reset()
    
    @property
    def log_df(self):
        return pd.DataFrame(columns=self.names, data=self._log)

    def before_fit(self):
        self.reset()
        self._log = []
        self.learner.metrics = self

    def before_epoch(self): self.reset()

    def before_loss(self):
        if (self.train and self.learner.training) or (not self.train and not self.learner.training):
            for metric in self.metrics:
                metric.update(self.learner.preds.detach().clone().cpu(), self.learner.yb.clone().cpu())
    
    def after_epoch(self):
        self._log.append([metric.compute().item() for metric in self.metrics])

# %% ../nbs/00_core.ipynb 12
class ProgressCB(Callback):
    "Log and display training infos."
    order = MetricCB.order + 1

    def before_fit(self):
        cols = (['train_loss']
                + (['test_loss'] if self.learner.dls[1] != [] else [])
                + (self.learner.metrics.names if hasattr(self.learner, 'metrics') else [])
                + (self.learner.extra_log.all_names if hasattr(self.learner, 'extra_log') else [])
               )
        self._log = pd.DataFrame(columns=cols)
        self.disp_log = pd.DataFrame(columns=cols)
        self.disp_log_id = None
    
    def before_epoch(self):
        if self.disp_log_id is None: self.disp_log_id = display(self.disp_log, display_id=True)
        self._one_epoch = [[],[]]

    def before_backward(self):
        self._one_epoch[0].append(self.learner.loss.item()) # batch train_loss

    def after_loss(self):
        self._one_epoch[1].append(self.learner.loss.item()) # batch test_loss

    def after_epoch(self):
        self._log.loc[self.learner.epoch] = ([np.mean(o) for o in self._one_epoch if o != []]
                                             + (self.learner.metrics._log[-1] if hasattr(self.learner, 'metrics') else [])
                                             + (self.learner.extra_log._data if hasattr(self.learner, 'extra_log') else [])
                                            )
        if self.learner.epoch % self.learner.disp_every == 0:
            self.disp_log.loc[self.learner.epoch] = self._log.loc[self.learner.epoch]
            self.disp_log_id.update(self.disp_log)
        
    def after_fit(self):
        self.learner.log = self._log

# %% ../nbs/00_core.ipynb 13
class BaseLogCB(Callback):
    "Base class. Log extra (other than standard train/test loss and metrics) infos."
    order = ProgressCB.order-1

    def __init__(self, names: list[list],  # Names of logged entries for each `func`
                 funcs: list[callable],    # Funcstions to get the logged entries; each `f()` should take a single input `learner` and outputs a list/tuple of values
                 keep: bool=False          # Keep a local log; logs can be found in `self.learner.log`
                ):
        self.names,self.funcs,self.keep = names,funcs,keep
        self._data = []
    
    @property
    def all_names(self):
        return [oi for o in self.names for oi in o]
    
    @property
    def log_df(self):
        if not self.keep: print('No log found.'); return
        return pd.DataFrame(columns=self.all_names, data=self._log)

    def before_fit(self):
        self.learner.extra_log = self
        if self.keep: self._log = []

    def before_epoch(self): self._data.clear()
    def after_epoch(self):
        for f in self.funcs:
            val = f(self.learner)
            if isinstance(val, (tuple, list)): self._data.extend(val)
            elif isinstance(val, (int, float, bool, str)): self._data.append(val)
            else: raise TypeError('Log function output should be tuple/list/scalar-like/string.')
        if self.keep: self._log.append(self._data.copy())
            

# %% ../nbs/00_core.ipynb 14
class ClipGradCB(Callback):
    "Clip the gradient norm."
    def __init__(self, max_norm=1, norm_type=2, **kwargs):
        self._norm = lambda x: nn.utils.clip_grad_norm_(x, max_norm, norm_type, **kwargs)
    def before_step(self): self._norm(self.learner.model.parameters())

# %% ../nbs/00_core.ipynb 15
class LRCB(Callback):
    "Learning rate callback."
    def __init__(self, scheduler): self.scheduler = scheduler
    def after_step(self): self.scheduler.step()

# %% ../nbs/00_core.ipynb 17
class Hook():
    "From `fastai`. Register a hook to `m` with `func`."
    def __init__(self, m, func, forward=True, detach=True, cpu=True):
        register = m.register_forward_hook if forward else m.register_full_backward_hook
        self.hook,self.func = register(self.hook_func),func
        self.stored,self.removed = None,False
        self.detach,self.cpu = detach,cpu

    def hook_func(self, m, i, o):
        if self.detach: (i,o) = to_detach(i),to_detach(o)
        if self.cpu: (i,o) = to_cpu(i),to_cpu(o)
        self.stored = self.func(m, i, o)

    def remove(self):
        if not self.removed:
            self.hook.remove()
            self.removed = True
    # context manager
    def __enter__(self, *args): return self
    def __exit__(self, *args): self.remove()

# %% ../nbs/00_core.ipynb 18
class Hooks():
    "From `fastai`. Register `Hook` to models in `ms`."
    def __init__(self, ms, func, forward=True, detach=True, cpu=True):
        self.hooks = [Hook(m, func, forward, detach, cpu) for m in ms]

    def __getitem__(self,i): return self.hooks[i]
    def __len__(self):       return len(self.hooks)
    def __iter__(self):      return iter(self.hooks)
    @property
    def stored(self):        return [o.stored for o in self]

    def remove(self):
        for h in self.hooks: h.remove()

    def __enter__(self, *args): return self
    def __exit__ (self, *args): self.remove()

# %% ../nbs/00_core.ipynb 21
class Learner():
    "One place to train/test a model."
    _default_cbs = [DeviceCB(), ProgressCB()]
    def __init__(self, model: nn.Module, # The model to be trained
                 dls: tuple|list,        # The dataloaders used for training and testing
                 opt,                    # The optimizer used to update model's parameters
                 loss_func,              # The loss function
                 cbs=[],                 # Callbacks called in `order`
                 disp_every: int=1,      # Display log every `disp_every` epochs
                 device=torch.device('cpu')
                ):
        self.model,self.dls,self.opt,self.device = model,dls,opt,device
        self.disp_every = disp_every
        self.loss_func = loss_func
        self.cbs = sorted(list(cbs) + self._default_cbs, key=lambda o: o.order) # sort callbacks according to their `order`
        for cb in self.cbs     : cb.learner  = self
    @property
    def training(self):
        return self.model.training

    def do_one_batch(self, train):
        self('before_batch')
        self.xb,self.yb = self.batch
        self('before_pred')
        self.preds = self.model(self.xb)
        self('before_loss')
        self.loss = self.loss_func(self.preds, self.yb)
        if train:
            self('before_backward')
            self.opt.zero_grad()
            self.loss.backward()
            self('before_step')
            self.opt.step()
            self('after_step')
        else:
            self('after_loss')
        self('after_batch')

    def do_one_epoch(self):
        self('before_epoch')
        ### training ###
        self('before_train')
        # for self.batch in tqdm(self.dls[0], desc='Train', leave=False):
        for self.batch in self.dls[0]:
            self.model.train()
            self.do_one_batch(True)
            self.n_iters += 1
        ### testing ###
        self('before_test')
        # for self.batch in tqdm(self.dls[1], desc='Test', leave=False):
        for self.batch in self.dls[1]:
            self.model.eval()
            with torch.inference_mode():
                self.do_one_batch(False)
        self('after_epoch')

    def fit(self, n_epochs: int=1):
        self('before_fit')
        self.n_epochs = n_epochs
        self.n_iters = 0
        for self.epoch in tqdm(range(n_epochs), desc='Epochs'):
            self.do_one_epoch()
        self('after_fit')

    def predict(self, x):
        "Predict on an input instance."
        self.model.eval()
        with torch.inference_mode():
            try:
                pred = self.model(x)
            except:
                pred = self.model(x.unsqueeze(0))
            return pred

    def predict_batch(self, xb=None):
        "Predict on a batch."
        if xb is None:
            xb = self.dls[0].one_batch()[0] if self.dls[1] == [] else self.dls[1].one_batch()[0]
        self.model.eval()
        with torch.inference_mode():
            preds = self.model(xb)
        return preds
        
    def __call__(self, name):
        for cb in self.cbs: getattr(cb, name, noop)()

# %% ../nbs/00_core.ipynb 24
class Dataloader(DataLoader):
    "Extension to `torch.utils.data.DataLoader`, to work with huggingface's `Dataset`."
    def __init__(self, get_xy: callable, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.get_xy = get_xy
    
    def __iter__(self):
        it = super().__iter__()
        def _f():
            for o in it:
                yield tuple(self.get_xy(o))
        return _f()

    def one_batch(self):
        return next(iter(self))

# %% ../nbs/00_core.ipynb 25
def mk_dls_from_ds(ds,                        # Huggingface dataset
                   get_xy: callable,          # A function to get (input, target) from a dict 
                   fields=['train', 'test'],  # Dict keys to split the dataset
                   bs=[64, 64],               # Batch sizes
                   shuffle=True,              # Shuffle the training set
                  ):
    "Create train-test dataloaders."
    if not isinstance(ds, (tuple, list)):
        return (Dataloader(get_xy, dataset=ds[fields[0]], batch_size=bs[0], shuffle=shuffle),
                Dataloader(get_xy, dataset=ds[fields[1]], batch_size=bs[1], shuffle=False))
    else:
        return (Dataloader(get_xy, dataset=ds[0], batch_size=bs[0], shuffle=shuffle),
                Dataloader(get_xy, dataset=ds[1], batch_size=bs[1], shuffle=False))

# %% ../nbs/00_core.ipynb 26
def mk_dls_from_hub(name: str,                 # Name/path of the dataset
                    get_xy: callable,          # A function to get (input, target) from a dict
                    fields=['train', 'test'],  # Dict keys to split the dataset
                    sz=[None, None],           # Sizes of train and test set, if `None` then returns all
                    bs=[64, 64],               # Batch sizes
                    shuffle=True,              # Shuffle the training set
                    device=None
                   ):
    "Conveience method to create train-test dataloaders from huggingface hub."
    ds = load_dataset(name, device=device, trust_remote_code=True)
    train = Dataset.from_dict(ds[fields[0]][:sz[0]]).with_format('torch') if sz[0] is not None else ds[fields[0]].with_format('torch')
    test  = Dataset.from_dict(ds[fields[1]][:sz[1]]).with_format('torch') if sz[1] is not None else ds[fields[1]].with_format('torch')
    return mk_dls_from_ds([train, test], get_xy, bs=bs, shuffle=shuffle)

# %% ../nbs/00_core.ipynb 27
from sklearn.preprocessing import StandardScaler

# %% ../nbs/00_core.ipynb 28
class Scaler():
    "Simple wrapper of `sklearn.preprocessing.StandardScaler`."
    def __init__(self, data: list|np.ndarray, **kwargs):
        self.shape = np.shape(data)
        self.scaler = StandardScaler().fit(np.reshape(data, (self.shape[0],-1)), **kwargs)
    
    def xfm(self, data):
        _shape = np.shape(data)
        assert np.all(_shape[1:] == self.shape[1:])
        return self.scaler.transform(np.reshape(data, (_shape[0],-1))).reshape(_shape)
    
    def inv_xfm(self, data):
        _shape = np.shape(data)
        assert np.all(_shape[1:] == self.shape[1:])
        return self.scaler.inverse_transform(np.reshape(data, (_shape[0],-1))).reshape(_shape)
