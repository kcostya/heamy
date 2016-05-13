# coding:utf-8
import hashlib
import logging

import pandas as pd
import inspect

from sklearn.cross_validation import train_test_split, StratifiedKFold, KFold

from heamy.cache import Cache, numpy_buffer
from heamy.helpers import idx

logger = logging.getLogger('heamy.dataset')


class Dataset(object):
    """Dataset wrapper.

    Parameters
    ----------
    X_train : pd.DataFrame or np.ndarray, optional
    y_train : pd.DataFrame, pd.Series or np.ndarray, optional
    X_test : pd.DataFrame or np.ndarray, optional
    y_test : pd.DataFrame, pd.Series or np.ndarray, optional
    preprocessor: function, optional
        A callable function that returns preprocessed data.

        If `use_cache=True` then preprocessing step will be cached until function code is changed.
    use_cache : bool, default True

    Examples
    ----------
    >>> # function-based definition
    >>> from sklearn.datasets import load_boston
    >>> def boston_dataset():
    >>>     data = load_boston()
    >>>     X, y = data['data'], data['target']
    >>>     X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.1, random_state=111)
    >>>     return X_train, y_train, X_test, y_test
    >>> dataset = Dataset(preprocessor=boston_dataset)

    >>> # class-based definition
    >>> class BostonDataset(Dataset):
    >>> def preprocess(self):
    >>>     data = load_boston()
    >>>     X, y = data['data'], data['target']
    >>>     X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.1, random_state=111)
    >>>     return X_train, y_train, X_test, y_test
    """
    def __init__(self, X_train=None, y_train=None, X_test=None, y_test=None, preprocessor=None, use_cache=True):
        self._hash = None
        self.use_cache = use_cache
        self._preprocessor = preprocessor
        self._setup_data(X_train, y_train, X_test, y_test)

        if not ((X_train is not None) and (y_train is not None)):
            self._process_data()

        self._check_input()

    def _check_input(self):
        if (self._X_train is None) or (self._y_train is None):
            raise ValueError("Missing 2 required arrays: X_train and y_train.")

        if self._X_train.shape[0] != self._y_train.shape[0]:
            raise ValueError("Found arrays with inconsistent numbers of samples: X_train(%s), y_train(%s)" %
                             (self._X_train.shape[0], self._y_train.shape[0]))

        if (self._y_test is not None and self._X_test is not None) and (self._X_test.shape[0] != self._y_test.shape[0]):
            raise ValueError("Found arrays with inconsistent numbers of samples: X_test(%s), y_test(%s)" %
                             (self._X_test.shape[0], self._y_test.shape[0]))

        if (self._X_test is not None) and (self._X_train.shape[1] != self._X_test.shape[1]):
            raise ValueError("Found arrays with inconsistent numbers of features: X_train(%s), X_test(%s)" %
                             (self._X_train.shape[1], self._X_test.shape[1]))

    def _process_data(self):
        if hasattr(self.__class__, 'preprocess'):
            self._preprocessor = self.preprocess

        if callable(self._preprocessor):
            if (not self.use_cache) or (self.use_cache and not self._load_cache()):
                data = self._preprocessor()
                if isinstance(data, (list, tuple)):
                    self._setup_data(*data)
                elif isinstance(data, dict):
                    self._setup_data(**data)
                self._cache()

    def _load_cache(self):
        cache = Cache(self.hash, prefix='d')
        if cache.available:
            logger.info('Loading %s from cache.' % (self.__repr__()))

            self._X_train = cache.retrieve('X_train')
            self._y_train = cache.retrieve('y_train')

            self._X_test = cache.retrieve('X_test')
            self._y_test = cache.retrieve('y_test')
            return True
        else:
            return False

    def _cache(self):
        if callable(self._preprocessor):
            cache = Cache(self.hash, prefix='d')

            cache.store('X_train', self._X_train)
            cache.store('y_train', self._y_train)

            if self._X_test is not None:
                cache.store('X_test', self._X_test)

            if self._y_test is not None:
                cache.store('y_test', self._y_test)
            return True
        else:
            logger.warning("%s can not be cached." % self.__repr__())
            return False

    @property
    def name(self):
        if hasattr(self.__class__, 'preprocess') or self._preprocessor is None:
            name = self.__class__.__name__
        else:
            name = self._preprocessor.__name__

        return name

    def __repr__(self):
        return '%s(%s)' % (self.name, self.hash)

    def _setup_data(self, X_train=None, y_train=None, X_test=None, y_test=None):

        self._X_train = X_train
        if isinstance(y_train, (pd.Series, pd.DataFrame)):
            self._y_train = y_train.values
        else:
            self._y_train = y_train

        self._X_test = X_test
        self._y_test = y_test

    def split(self, test_size=0.1, stratify=False, save=False, seed=33, indices=None):
        """Splits train set into two parts (train/test).

        Parameters
        ----------
        test_size : float, default 0.1
        stratify : bool, default False
        save : bool, default False
            If `True` then dataset's train/test will be replaced with new data.
        seed : int, default 33
        indices : list(np.ndarray,np.ndarray), default None
            Two numpy arrays that contain indices for train/test slicing.

        Returns
        -------
        X_train : np.ndarray
        y_train : np.ndarray
        X_test : np.ndarray
        y_test : np.ndarray

        Examples
        --------

        >>> train_index = np.array(range(250))
        >>> test_index = np.array(range(250,333))
        >>> res = dataset.split(indices=(train_index,test_index))

        >>> res = dataset.split(test_size=0.3,seed=1111)
        """
        if stratify:
            stratify = self.y_train
        else:
            stratify = None

        if indices is None:
            X_train, X_test, y_train, y_test = train_test_split(self.X_train, self._y_train,
                                                                test_size=test_size,
                                                                random_state=seed,
                                                                stratify=stratify, )
        else:
            X_train, y_train = idx(self.X_train, indices[0]), self.y_train[indices[0]]
            X_test, y_test = idx(self.X_train, indices[1]), self.y_train[indices[1]]

        if save:
            self._X_train, self._X_test, self._y_train, self._y_test = X_train, X_test, y_train, y_test

        return X_train, y_train, X_test, y_test

    def kfold(self, k=5, stratify=False, shuffle=True, seed=33):
        """K-Folds cross validation iterator.

        Parameters
        ----------
        k : int, default 5
        stratify : bool, default False
        shuffle : bool, default True
        seed : int, default 33

        Yields
        -------
        X_train, y_train, X_test, y_test, train_index, test_index
        """
        if stratify:
            kf = StratifiedKFold(y=self.y_train, n_folds=k, random_state=seed, shuffle=shuffle)
        else:
            kf = KFold(self.y_train.shape[0], n_folds=k, random_state=seed, shuffle=shuffle)

        for train_index, test_index in kf:
            X_train, y_train = idx(self.X_train, train_index), self.y_train[train_index]
            X_test, y_test = idx(self.X_train, test_index), self.y_train[test_index]
            yield X_train, y_train, X_test, y_test, train_index, test_index

    @property
    def X_train(self):
        return self._X_train

    @property
    def y_train(self):
        return self._y_train

    @property
    def X_test(self):
        if self._X_test is not None:
            return self._X_test
        else:
            raise NameError('Name X_test is not defined.')

    @property
    def y_test(self):
        if self._y_test is not None:
            return self._y_test
        else:
            raise NameError('Name y_test is not defined.')

    @property
    def hash(self):
        if self._hash is None:
            m = hashlib.new('md5')
            if self._preprocessor is None:
                m.update(numpy_buffer(self._X_train))
                m.update(numpy_buffer(self._y_train))
                if self._X_test is not None:
                    m.update(numpy_buffer(self._X_test))
                if self._y_test is not None:
                    m.update(numpy_buffer(self._y_test))
            elif callable(self._preprocessor):
                m.update(inspect.getsource(self._preprocessor).encode('utf-8'))

            self._hash = m.hexdigest()

        return self._hash