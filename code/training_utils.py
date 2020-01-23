#!/usr/bin/env python3
# -*- coding: utf-8 -*-

## codebase ##
################################################################################
import glob, os, sys
from ase import io
import numpy as np
import shutil

# Database Module
from ase.db import connect

# Math Module
from random import shuffle
from itertools import chain
from scipy.optimize import basinhopping

# AMP Module
from amp import Amp
from amp.model.neuralnetwork import NeuralNetwork
from amp.descriptor.gaussian import Gaussian, make_symmetry_functions
from amp.utilities import hash_images, get_hash
from amp.model.neuralnetwork import NodePlot
from amp.regression import Regressor
from amp.model import LossFunction

# AMP analysis
from amp.descriptor.analysis import FingerprintPlot
from amp.analysis import plot_parity
from amp.analysis import plot_sensitivity
from amp.analysis import plot_convergence

# Visual
import matplotlib.pyplot as plt
colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
from ase.visualize import view

# sklearn module
sys.path.insert(0,"/usr/local/lib/python3.7/site-packages/")
from sklearn.metrics import mean_squared_error


class Database_tools:
    """ ASE Database tools used for sampling data from raw DFT calculations
        Init: specify directory path of database, database name
        TODO: #1 add read vasprun.xml file functionality
    """
    def __init__(self, db_path, db_name, dataset='all.traj', training_traj='trainset.traj', validation_traj='validset.traj'):
        self.path = db_path
        self.name = db_name
        self.dataset = dataset
        self.training_traj = training_traj
        self.validation_traj = validation_traj

    def db_selector(self, **kwargs):
        """ Extract traj list of atom configurations from database
            Inputs: kwargs: dictionary of db search key words
            Output: atoms trajectory list
        """
        #remove the old folders
        if os.path.isfile(self.dataset):
            os.remove(self.dataset)
            os.remove(self.training_traj)
            os.remove(self.validation_traj)
        else:
            print('No existed traj files detected')
        traj = []
        db = connect(self.path + self.name)
        dict_v = [v for k,v in kwargs.items()]
        dict_v = ", ".join(dict_v) # list --> string
        for row in db.select(dict_v):
            atoms = db.get_atoms(id=row.id)
            traj.append(atoms)
        return traj

    def train_test_split(self, shuffle_mode, traj, training_weight):
        """ Inputs: mode = 0 or 1: randomly selection or dummy selection
                    traj: traj file as a list from db_selector function
                    training_weight: weight percentage of train-test split
            Outputs: length of traj file, training traj, valid traj
        """
        if shuffle_mode == True:
            shuffle(traj)
        elif shuffle_mode == False:
            pass
        len_traj = len(traj)
        len_train = round(training_weight*len(traj))
        traj_train = traj[:len_train]
        traj_valid = traj[len_train:]
        return len_traj, traj_train, traj_valid

class Fp_analysis_tools:
    """ Some notes about the fp data structure:
        The key of fp --> each of the atoms, 43 in total
            the hash of fp: 0 --> the element type of atom e.g. oxygen
            1 --> each fp values, 36 in total, refering to the Gaussian data
        if fp = descriptor.fingerprints[hash]:
            fp gives # of images, each image contains list of all 43 elements, each element
            has 36 fp values, which could be tested by:
            fp = descriptor.fingerprints[hash][atom_index][1]
            print(fp, len(fp)))
        The number of fps caculation rule:
            G2: 4 eta-parameters X 3 different type of atoms = 12 fps
            G4: 1 eta-parameter X 2 zeta-parameter X 2 gamma-parameter X 6 (A3_2) types of
            2-atom interactions = 24 fps
            --> all together 36 fps
    """
    def __init__(self, metal, mode, ):
        """ Inputs: #1 type of metal nanocluster
                    #2 mode=0: only the metal nanocluster
                    mode=1: netal nanocluster with zeolite framework
        """
        self.metal = metal
        self.mode = mode

    def descriptor_generator(self, G2_etas, G4_etas, G4_zetas, G4_gammas):
        """ Use this function solely for Amp calculator set-up
            Inputs: #1-4 Use Gaussian Functions as fingerprints kernel
                    Change the parameters of G2 and G4
            Output: the descriptor, G data structure
        """
        elements = [self.metal]
        if self.mode == 0:
            pass
        elif self.mode == 1:
            elements.append('Si')
            elements.append('O')
        # only
        G = make_symmetry_functions(elements=elements, type='G2',
                                    etas = G2_etas)
        G += make_symmetry_functions(elements=elements, type='G4',
                                     etas = G4_etas,
                                     zetas = G4_zetas,
                                     gammas = G4_gammas)
        my_Gs = {self.metal:G}
        if self.mode == 0:
            pass
        elif self.mode == 1:
            my_Gs.update({'Si':G, 'O':G})
        descriptor = Gaussian(Gs = my_Gs)
        return descriptor, G

    def calc_fp(self, descriptor, images):
        """ Inputs: #1 descriptor from fcn --> descriptor_generator
                    #2 images by ase.io.read() .traj file
        """
        images = hash_images(images)
        descriptor.calculate_fingerprints(images)
        return descriptor, images

    def fp_values_extractor(self, atom_index, G, hash, descriptor, fig_name):
        """ Inputs: #1 atom_index: fp of which number of atom in the system
                    e.g. atom_index = 0 the first O element
                    #2 G: symmetry functions, return from fcn --> descriptor_generator
                    #3 hash: receive the arg from emurating the images from --> calc_fp
                    #4 descriptor from fcn --> calc_fp
                    #5 figure name
            Outputs: print out information about the fingerprints
                    the scatter plot of the fp values
        """
        fp = descriptor.fingerprints[hash][atom_index][1]
        for j, val in enumerate(fp):
            g = G[j]
            if g['type'] == 'G2':
                ele = g['element']
            elif g['type'] == 'G4':
                ele = g['elements']
            print(j, g['type'], ele, g['eta'], val)

            if self.metal in ele:
                my_marker = 'o'
            else:
                my_marker = 'x'
            plt.plot(j, val, my_marker)
            plt.savefig(fig_name)

    def get_extreme_value_fp(self, descriptor, images):
        """ Extract the maximum and minimum values of all the fingerprints generated
            Inputs: enumerating the images returned by fcn --> calc_fp
            Outputs: print out maximum and minimum values of fp
        """
        for index, hash in enumerate(images.keys()):
            fp = descriptor.fingerprints[hash]#[0][1] all the information of fp
            max_all_image_fp_list = [] # max fp value of all images
            min_all_image_fp_list = [] # min fp valueof all images
            for i in fp:
                #i = each atom and its 36 fp values
                #print(i[1]) #5(image)X43(row)X36(column)
                max_i_fp = max(i[1]) #i[0] --> atom type, i[1] --> 36 fp values
                min_i_fp = min(i[1])
                max_all_image_fp_list.append(max_i_fp)
                min_all_image_fp_list.append(min_i_fp)

            max_fp = max(max_all_image_fp_list)
            min_fp = min(min_all_image_fp_list)
            print("The maximum value of the fp is " + str(max_fp))
            print("The minimum value of the fp is " + str(min_fp))
        return max_fp, min_fp

    def fp_barplot(self, atom_index, G, hash, descriptor, fig_name, title):
        """ make sure that's for one image, or make a gif for images
            Makes a barplot of the fingerprint about certain atom
            Input: #1-5 same as inputs of fcn --> fp_values_extractor
            #6 title of each sub-polt
        """
        fp = descriptor.fingerprints[hash][atom_index][1] #list
        fig, ax = plt.subplots()
        G2_val = []
        G4_val = []
        metal_index_list = [] #lists indicate indices of zeo or metal
        zeo_index_list = []
        metal_ele_list = [] # lists indicate zeo or metal
        zeo_ele_list = []

        for j, val in enumerate(fp):
            g = G[j]
            if g['type'] == 'G2':
                G2_val.append(val)
                ele = g['element']
            elif g['type'] == 'G4':
                G4_val.append(val)
                ele = g['elements']

            if self.mode == 0:
                metal_index_list.append(j)
                metal_ele_list.append(val)
            elif self.mode == 1:
                if self.metal in ele:
                    metal_index_list.append(j)
                    metal_ele_list.append(val)
                else:
                    zeo_index_list.append(j)
                    zeo_ele_list.append(val)

        ax.bar(range(len(G2_val)), G2_val, label = "G2") #set the x-y axis
        ax.bar(np.arange(len(G4_val)) + len(G2_val), G4_val, label = "G4")
        ax.set_title(title)
        ax.set_ylim(0., 13.)
        ax.set_xlabel('fingerprint')
        ax.set_ylabel('value')
        ax.scatter(metal_index_list, metal_ele_list, marker = 'o', color='purple', label='metal atom')
        if self.mode == 1:
            ax.scatter(zeo_index_list, zeo_ele_list, marker = 'x', color='purple', label='only zeo atoms')
        ax.legend()
        fig.savefig(fig_name)

class Train_tools:
    """ Training module using Machine learning for atomistic system model energies/forces fitting tasks
        Use coupled with Fp_values_extractor module for generating descriptor.
    """
    def __init__(self, descriptor, path,  force_option, training_traj='trainset.traj', validation_traj='validset.traj'):
        """ Init: Based on the fcn --> descriptor_generator in Fp_values_extractor module, returned descriptor
            used in this fcn.
            force_option: choose if want to turn on force training
        """
        self.descriptor = descriptor
        self.path = path
        self.training_traj = training_traj
        self.validation_traj = validation_traj
        self.force_option = force_option

    def read_traj(self, trainset_index=':', validset_index=':'):
        """ .traj files input, specify selecting range of trajectories
        """
        training_traj = io.read(self.path + self.training_traj, trainset_index)
        validation_traj = io.read(self.path + self.validation_traj, validset_index)
        return training_traj, validation_traj

    def train_amp_setup(self, trigger, training_traj, **kwargs):
        """ Adjusting convergence parameters
            how tightly the energy and/or forces are converged --> adjust the LossFunction
            To change how the code manages the regression process --> use the Regressor class
            Inputs: dictionary of neural-net parameters
            dictionary tructure:
                #1 'hiddenlayers': NN architecture
                #2 'optimizer'
                #3 'lossprime'：True if want gradient-based
                #4 'convergence': convergence parameters
                #5 force_coefficient: control the relative weighting of the energy and force RMSEs used
                in the path to convergence
            Output: Trained calculator

            TDOD: #1 update optimizer
                  #2 update bootstrap-stat
                  #3 update more ML model
                  #4 updateb better method than decompose the nn_features_dict
        """
        nn_dict = [v for k,v in kwargs.items()]
        calc = Amp(descriptor = self.descriptor, model = NeuralNetwork(hiddenlayers = nn_dict[0], checkpoints=14),
                   label='amp')
        regressor = Regressor(optimizer=nn_dict[1], lossprime=nn_dict[2])
        calc.model.regressor = regressor
        if self.force_option == False:
            calc.model.lossfunction = LossFunction(convergence=nn_dict[3])
        elif self.force_option == True:
            calc.model.lossfunction = LossFunction(convergence=nn_dict[3], force_coefficient=nn_dict[4])
        if trigger == True:
            calc.train(images=training_traj)
        else:
            print("Training NOT Start")
        return calc

    def get_dft_energy(self, training_traj, validation_traj, rel_option):
        """ Inputs: train-valid sets from fcn --> read_traj
            Outputs: choose to return raw or/both relative dft energies
        """
        e_dft_train = np.array([atoms.get_potential_energy() for atoms in training_traj])
        e_dft_validation = np.array([atoms.get_potential_energy() for atoms in validation_traj])
        if rel_option == False:
            return e_dft_train, e_dft_validation
        elif rel_option == True:
            e_dft = np.concatenate((e_dft_train,e_dft_validation))
            rel_e_dft_train = e_dft_train - min(e_dft)
            rel_e_dft_validation = e_dft_validation - min(e_dft)
            return e_dft_train, e_dft_validation, rel_e_dft_train, rel_e_dft_validation

    def get_dft_force(self, training_traj, validation_traj, rel_option, norm_option):
        """ Inputs: train-valid sets from fcn --> read_traj
            Outputs: forces at X-Y-Z axises
                    choose to return raw or/both relative dft forces
                    choose to return total force
        """
        if self.force_option == False:
            raise ValueError('Force_option is not turned on!')
        else:
            pass
        # assin DFT calculator
        f_dft_train = np.array([atoms.get_forces() for atoms in training_traj])
        f_dft_validation = np.array([atoms.get_forces() for atoms in validation_traj])

        # decompose forces into X-Y-Z axises
        x_train_force_list = []
        y_train_force_list = []
        z_train_force_list = []
        merged_f_dft_train = list(chain(*f_dft_train))
        for i in merged_f_dft_train:
            x_train_force_list.append(i[0])
            y_train_force_list.append(i[1])
            z_train_force_list.append(i[2])

        x_valid_force_list = []
        y_valid_force_list = []
        z_valid_force_list = []
        merged_f_dft_valid = list(chain(*f_dft_validation))
        for i in merged_f_dft_valid:
            x_valid_force_list.append(i[0])
            y_valid_force_list.append(i[1])
            z_valid_force_list.append(i[2])

        # translate to total force
        if norm_option == True:
            f_dft_train = [np.linalg.norm(forces) for forces in f_dft_train]
            f_dft_validation = [np.linalg.norm(forces) for forces in f_dft_validation]
            # option to get relative forces
            f_dft = np.concatenate((f_dft_train, f_dft_validation))
            rel_f_dft_train = f_dft_train - min(f_dft)
            rel_f_dft_valid = f_dft_validation - min(f_dft)
            return f_dft_train, f_dft_validation, rel_f_dft_train, rel_f_dft_validation

        elif (norm_option == False and rel_option == True):
            f_x_dft = np.concatenate((x_train_force_list, x_valid_force_list))
            rel_f_x_dft_train = x_train_force_list - min(f_x_dft)
            rel_f_x_dft_valid = x_valid_force_list - min(f_x_dft)
            f_y_dft = np.concatenate((y_train_force_list, y_valid_force_list))
            rel_f_y_dft_train = y_train_force_list - min(f_y_dft)
            rel_f_y_dft_valid = y_valid_force_list - min(f_y_dft)
            f_z_dft = np.concatenate((z_train_force_list, z_valid_force_list))
            rel_f_z_dft_train = z_train_force_list - min(f_z_dft)
            rel_f_z_dft_valid = z_valid_force_list - min(f_z_dft)
            return (rel_f_x_dft_train, rel_f_x_dft_valid, rel_f_y_dft_train,
                    rel_f_y_dft_valid, rel_f_z_dft_train, rel_f_z_dft_valid)

        elif (norm_option == False and rel_option == False):
            return (x_train_force_list, x_valid_force_list, y_train_force_list,
                    y_valid_force_list, z_train_force_list, z_valid_force_list)

    def get_neuralnet_energy(self, calc, training_traj, validation_traj, rel_option):
        """ Inputs: trained AMP calculator returned from fcn --> train_amp_setup
            Outputs: raw and/or relative AMP energies
        """
        e_amp_train = []
        e_amp_validation = []
        for atoms in training_traj:
            atoms.set_calculator(calc)
            e_train = atoms.get_potential_energy()
            e_amp_train.append(e_train)
        for atoms in validation_traj:
            atoms.set_calculator(calc)
            e_valid = atoms.get_potential_energy()
            e_amp_validation.append(e_valid)
        if rel_option == True:
            e_amp = np.concatenate((e_amp_train, e_amp_validation))
            rel_e_amp_train = e_amp_train - min(e_amp)
            rel_e_amp_validation = e_amp_validation - min(e_amp)
            return e_amp_train, e_amp_validation, rel_e_amp_train, rel_e_amp_validation
        elif rel_option == False:
            return e_amp_train, e_amp_validation

    def get_neuralnet_force(self, calc, training_traj, validation_traj, rel_option, norm_option):
        """ Inputs: trained AMP calculator
            Outputs: raw and relative AMP forces
        """
        if self.force_option == False:
            raise ValueError('Force_option is not turned on!')
        else:
            pass
        # assign AMP calculator
        f_amp_train = []
        f_amp_validation = []
        for atoms in training_traj:
            atoms.set_calculator(calc)
            f_train = atoms.get_forces()
            f_amp_train.append(f_train)
        for atoms in validation_traj:
            atoms.set_calculator(calc)
            f_valid = atoms.get_forces()
            f_amp_validation.append(f_valid)

        # decompose forces into X-Y-Z axises
        x_train_force_list = []
        y_train_force_list = []
        z_train_force_list = []
        merged_f_amp_train = list(chain(*f_amp_train))
        for i in merged_f_amp_train:
            x_train_force_list.append(i[0])
            y_train_force_list.append(i[1])
            z_train_force_list.append(i[2])

        x_valid_force_list = []
        y_valid_force_list = []
        z_valid_force_list = []
        merged_f_amp_valid = list(chain(*f_amp_validation))
        for i in merged_f_amp_valid:
            x_valid_force_list.append(i[0])
            y_valid_force_list.append(i[1])
            z_valid_force_list.append(i[2])

        # translate to total force
        if norm_option == True:
            f_amp_train = [np.linalg.norm(forces) for forces in f_amp_train]
            f_amp_validation = [np.linalg.norm(forces) for forces in f_amp_validation]
            # option to get relative forces
            f_amp = np.concatenate((f_amp_train, f_amp_validation))
            rel_f_amp_train = f_amp_train - min(f_amp)
            rel_f_amp_valid = f_amp_validation - min(f_amp)
            return f_amp_train, f_amp_validation, rel_f_amp_train, rel_f_amp_validation

        elif (norm_option == False and rel_option == True):
            f_x_amp = np.concatenate((x_train_force_list, x_valid_force_list))
            rel_f_x_amp_train = x_train_force_list - min(f_x_amp)
            rel_f_x_amp_valid = x_valid_force_list - min(f_x_amp)
            f_y_amp = np.concatenate((y_train_force_list, y_valid_force_list))
            rel_f_y_amp_train = y_train_force_list - min(f_y_amp)
            rel_f_y_amp_valid = y_valid_force_list - min(f_y_amp)
            f_z_amp = np.concatenate((z_train_force_list, z_valid_force_list))
            rel_f_z_amp_train = z_train_force_list - min(f_z_amp)
            rel_f_z_amp_valid = z_valid_force_list - min(f_z_amp)
            return (rel_f_x_amp_train, rel_f_x_amp_valid, rel_f_y_amp_train,
                    rel_f_y_amp_valid, rel_f_z_amp_train, rel_f_z_amp_valid)

        elif (norm_option == False and rel_option == False):
            return (x_train_force_list, x_valid_force_list, y_train_force_list,
                    y_valid_force_list, z_train_force_list, z_valid_force_list)

    def fitting_energy_plot(self, e_dft_train, e_dft_validation, e_amp_train, e_amp_validation, fig_title):
        """ Inputs: train-valid dft/amp raw/rel energies
            Outputs: Figure 1: fitting results
                     Figure 2: Histogram of energy sampling
        """
        plt.figure(figsize=(6, 8))
        plt.subplot(2,1,1)
        plt.plot(e_dft_train,e_dft_train,'-k')
        plt.plot(e_dft_train,e_amp_train,'o',fillstyle='full',color=colors[0],label='training',markeredgecolor='k')
        plt.plot(e_dft_validation,e_amp_validation,'o',fillstyle='full',color=colors[1],label='validation',markeredgecolor='k')
        plt.legend()
        plt.xlabel('DFT energy, eV')
        plt.ylabel('ML-FF energy, eV')
        rms_valid = np.sqrt(mean_squared_error(e_dft_validation, e_amp_validation))
        rms_train = np.sqrt(mean_squared_error(e_dft_train, e_amp_train))
        #rms_valid_2 = np.sqrt(((e_amp_validation-e_dft_validation) ** 2).mean())
        #rms_train_2 = np.sqrt(((e_amp_train-e_dft_train) ** 2).mean())
        #print(rms_train_2, rms_valid_2)
        plt.title('RMSE train=%s, valid=%s' % (rms_train, rms_valid))

        plt.subplot(2,1,2)
        plt.hist(e_dft_train,color=colors[0], density = True, label = 'training')
        plt.hist(e_dft_validation,color=colors[1],alpha = 0.7, density = True, label = 'validation',ec='k')
        plt.xlabel('DFT energy, eV')
        plt.ylabel('Occurence frequency')
        plt.legend()
        plt.savefig('./'+ fig_title +'.png')
        return rms_train, rms_valid

    def fitting_force_plot(self, f_dft_train, f_dft_validation, f_amp_train, f_amp_validation, fig_title):
        """ Inputs: train-valid dft/amp raw/rel forces for a specific force axis
            Outputs: Figure 1: fitting results
                     Figure 2: Histogram of forces sampling
        """
        if self.force_option == False:
            raise ValueError('Force_option is not turned on!')
        else:
            pass

        plt.figure(figsize=(6, 8))
        plt.subplot(2,1,1)
        plt.plot(f_dft_train,f_dft_train,'-k')
        plt.plot(f_dft_train,f_amp_train,'o',fillstyle='full',color=colors[0],label='training',markeredgecolor='k')
        plt.plot(f_dft_validation,f_amp_validation,'o',fillstyle='full',color=colors[1],label='validation',markeredgecolor='k')
        plt.legend()
        plt.xlabel('DFT force, eV/Ang')
        plt.ylabel('ML-FF force, eV/Ang')
        rms_valid = np.sqrt(mean_squared_error(f_dft_validation, f_amp_validation))
        rms_train = np.sqrt(mean_squared_error(f_dft_train, f_amp_train))
        plt.title('RMSE train=%s, valid=%s' % (rms_train, rms_valid))

        plt.subplot(2,1,2)
        plt.hist(f_dft_train,color=colors[0], density = True, label = 'training')
        plt.hist(f_dft_validation,color=colors[1],alpha = 0.7, density = True, label = 'validation',ec='k')
        plt.xlabel('DFT force, eV/Ang')
        plt.ylabel('Occurence frequency')
        plt.legend()
        plt.savefig('./'+ fig_title +'.png')
        return rms_train, rms_valid

class Model_analysis:
    """ implemented convergence and parameters ananlysis for Atomistic Machine Learning task
    """
    def __init__(self, ):

    def 