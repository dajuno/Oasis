__author__ = 'Joakim Boe <joakim.bo@mn.uio.no>'
__date__ = '2015-02-04'
__copyright__ = 'Copyright (C) 2015 ' + __author__
__license__  = 'GNU Lesser GPL version 3 or any later version'

from DynamicModules import tophatfilter, lagrange_average, compute_Lij,\
        compute_Mij, compute_Qij, compute_Nij, dyn_u_ops
import DynamicLagrangian
import numpy as np

__all__ = ['les_setup', 'les_update']

def les_setup(u_, mesh, dt, krylov_solvers, V, assemble_matrix, CG1Function, nut_krylov_solver, 
        bcs, u_components, **NS_namespace):
    """
    Set up for solving the Germano Dynamic LES model applying
    scale dependent Lagrangian Averaging.
    """
    
    # The setup is 99% equal to DynamicLagrangian, hence use its les_setup
    dyn_dict = DynamicLagrangian.les_setup(**vars())
    
    # Add scale dep specific parameters
    JQN = dyn_dict["dummy"].copy()
    JQN[:] += 1E-32
    JNN = dyn_dict["dummy"].copy()
    JNN[:] += 1.
    
    Qij = [dyn_dict["dummy"].copy() for i in range(dyn_dict["dim"]**2)]
    Nij = [dyn_dict["dummy"].copy() for i in range(dyn_dict["dim"]**2)]

    # Update and return dict
    dyn_dict.update(JQN=JQN, JNN=JNN, Qij=Qij, Nij=Nij)

    return dyn_dict

def les_update(u_ab, u_components, nut_, nut_form, dt, CG1, tstep, 
            DynamicSmagorinsky, Cs, u_CG1, u_filtered, Lij, Mij,
            JLM, JMM, dim, tensdim, G_matr, G_under, ll,
            dummy, uiuj_pairs, Sijmats, Sijcomps, Sijfcomps, delta_CG1_sq, 
            Qij, Nij, JNN, JQN, Sij_sol, bcs_u_CG1, **NS_namespace): 

    # Check if Cs is to be computed, if not update nut_ and break
    if tstep%DynamicSmagorinsky["Cs_comp_step"] != 0:
        # Update nut_
        nut_()
        # Break function
        return
    
    # All velocity components must be interpolated to CG1 then filtered
    dyn_u_ops(**vars())

    # Compute Lij from dynamic modules function
    compute_Lij(u=u_CG1, uf=u_filtered, **vars())

    # Compute Mij from dynamic modules function
    alpha = 2.
    magS = compute_Mij(alphaval=alpha, u_nf=u_CG1, u_f=u_filtered, **vars())

    # Lagrange average Lij and Mij
    lagrange_average(J1=JLM, J2=JMM, Aij=Lij, Bij=Mij, **vars())

    # Now u needs to be filtered once more
    for i, ui in enumerate(u_components):
        # Filter
        tophatfilter(unfiltered=u_filtered[i].vector(),
                filtered=u_filtered[i].vector(), **vars())
        # Apply bcs
        [bc.apply(u_filtered[i].vector()) for bc in bcs_u_CG1[ui]]

    # Compute Qij from dynamic modules function
    compute_Qij(uf=u_filtered, **vars())

    # Compute Nij from dynamic modules function
    alpha = 4.
    compute_Nij(alphaval=alpha, u_f=u_filtered, **vars())

    # Lagrange average Qij and Nij
    lagrange_average(J1=JQN, J2=JNN, Aij=Qij, Bij=Nij, **vars())

    # UPDATE Cs**2 = (JLM*JMM)/beta, beta = JQN/JNN
    beta = (JQN.array()/JNN.array()).clip(min=0.125)
    Cs.vector().set_local(((JLM.array()/JMM.array())/beta).clip(max=0.09))
    Cs.vector().apply("insert")
    tophatfilter(unfiltered=Cs.vector(), filtered=Cs.vector(), N=2, weight=1, **vars())

    # Update nut_
    nut_.vector().zero()
    nut_.vector().axpy(1.0, Cs.vector() * delta_CG1_sq * magS)
    [bc.apply(nut_.vector()) for bc in nut_.bcs]
