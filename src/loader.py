import numpy as np
from pathlib import Path

from tensorflow.keras import utils
from albumentations import Compose, ElasticTransform, GridDistortion, CLAHE


class DataLoader(utils.Sequence):
    def __init__(
        self,
        mode="train",
        data_path="./prep/",
        valid_patient="L333",
        test_patient="L506",
        batch_size=8,
        train_pair=True,
        patch_size=256,
    ):
        super(DataLoader, self).__init__()
        assert mode in ["train", "valid", "test"]

        self.mode = mode
        self.data_path = data_path
        ldct_paths = sorted(Path(data_path).glob("*_ldct.npy"))
        ndct_paths = sorted(Path(data_path).glob("*_ndct.npy"))

        self.valid_patient = valid_patient
        self.test_patient = test_patient
        self.batch_size = batch_size
        self.train_pair = train_pair
        self.patch_size = patch_size

        self.ldct, self.ndct = self.load(ldct_paths, ndct_paths)
        if self.patch_size is not None:
            self.input_size = (patch_size, patch_size)
        else:
            self.input_size = self.ldct[0].shape
        self.indexes = np.arange(len(self.ldct))

        self.on_epoch_end()
        self.set_params()
        self.get_augmentation()

    def __len__(self):
        return len(self.ldct) // self.batch_size

    def __getitem__(self, idx):
        indexes = self.indexes[idx*self.batch_size : (idx+1)*self.batch_size]
        return self.getbatch(indexes)

    def on_epoch_end(self):
        if self.mode == "train":
            np.random.shuffle(self.indexes)

    def load(self, ldct_paths, ndct_paths):
        if self.mode == "train":
            ldct = [np.load(str(f)) for f in ldct_paths \
                if (self.valid_patient not in f.name) and (self.test_patient not in f.name)]
            ndct = [np.load(str(f)) for f in ndct_paths \
                if (self.valid_patient not in f.name) and (self.test_patient not in f.name)]
        elif self.mode == "valid":
            ldct = [np.load(str(f)) for f in ldct_paths if self.valid_patient in f.name]
            ndct = [np.load(str(f)) for f in ndct_paths if self.valid_patient in f.name]
        else:
            ldct = [np.load(str(f)) for f in ldct_paths if self.test_patient in f.name]
            ndct = [np.load(str(f)) for f in ndct_paths if self.test_patient in f.name]
        return ldct, ndct

    def set_params(self, grid_distort=0., elastic_deform=0., histeq=0.):
        self.prob_distort = grid_distort
        self.prob_elastic = elastic_deform
        self.prob_histeq = histeq

    def get_augmentation(self):
        self.aug = Compose([
            GridDistortion(num_steps=3, p=self.prob_distort),
            ElasticTransform(p=self.prob_elastic),
            CLAHE(p=self.prob_histeq)
        ])

    def getbatch(self, indexes):
        bx = np.zeros((self.batch_size, *self.input_size), dtype=np.float32)
        by = np.zeros((self.batch_size, *self.input_size), dtype=np.float32)

        for i, ldct_i in enumerate(indexes):
            if self.train_pair is True:
                ndct_i = ldct_i
            else:
                ndct_i = ldct_i-1 if ldct_i != 0 else ldct_i+1
            ldct, ndct = self.ldct[ldct_i], self.ndct[ndct_i]

            if self.mode == "train":
                data = {"image":ldct, "mask":ndct}
                aug = self.aug(**data)
                ldct, ndct = aug["image"], aug["mask"]
                ldct, ndct = self.random_crop(ldct, ndct)
            else:
                ldct = self.center_crop(ldct)
                ndct = self.center_crop(ndct)
            bx[i], by[i] = ldct, ndct
        return bx[...,np.newaxis], by[...,np.newaxis]

    def random_crop(self, img, mask):
        assert img.shape == mask.shape

        if isinstance(self.patch_size, int):
            crop_size = (self.patch_size, self.patch_size)

        h, w = img.shape
        x = np.random.randint(0, (h-crop_size[0]))
        y = np.random.randint(0, (w-crop_size[1]))

        cropped_img = img[
            x:(x+crop_size[0]),
            y:(y+crop_size[1])
        ]
        cropped_mask = mask[
            x:(x+crop_size[0]),
            y:(y+crop_size[1])
        ]
        return cropped_img, cropped_mask

    def center_crop(self, img):
        x, y = img.shape
        startx = x//2 - (self.patch_size//2)
        starty = y//2 - (self.patch_size//2)
        return img[startx:(startx+self.patch_size), \
                   starty:(starty+self.patch_size)]
