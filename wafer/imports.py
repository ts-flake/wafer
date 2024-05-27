from __future__ import annotations

from typing import Union,Optional,TypeVar,Callable,Any

import torch, torcheval
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader

from datasets import load_dataset, Dataset

import numpy as np
import pandas as pd
from PIL import Image
from matplotlib import animation
import matplotlib.pyplot as plt

import time
<<<<<<< HEAD
# from tqdm import tqdm
=======
>>>>>>> ef01f0d9d05e3e5b8f2c3ea9f9fae8f30d06c5e9
from tqdm.notebook import tqdm
from IPython.display import display, clear_output, HTML, SVG

def noop (x=None, *args, **kwargs):
    "Do nothing"
    return x