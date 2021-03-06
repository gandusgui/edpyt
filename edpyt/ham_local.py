from types import MethodType
import numpy as np

from numba import njit, prange
from numba.types import Array, float64, uint32, boolean

from edpyt.shared import unsigned_one as uone, unsiged_dt


@njit((Array(float64, 3, 'A', readonly=True),
       Array(float64, 2, 'C'),
       Array(uint32, 1, 'C'),
       Array(uint32, 1, 'C'),
       Array(float64, 1, 'C'),
       Array(float64, 1, 'C'),
       boolean,
       float64),
      parallel=True,cache=True)
def _build_ham_local(H, V, states_up, states_dw, vec_diag, z, hfmode=False, mu=0.):
    # ___                                   ___                              ___                             
    # \         e  (  n    +  n     )   +   \         U    n     n      +    \        (  n    +  n     ) V    (  n    +  n     )     
    # /__        i     i,up     i,dw        /__        i    i,up  i,dw       /__          i,up    i,dw     ij     j,up    j,dw  
    #     i                                     i                                i!=j                     
    dup = states_up.size
    dwn = states_dw.size
    n = V.shape[0]
    
    eupdiag = np.empty(n,np.float64)
    edwdiag = np.empty(n,np.float64)
    Vi = np.empty(n,np.float64)
    Vij = V.copy()
    for i in range(n):
        eupdiag[i] = H[0,i,i] + mu
        edwdiag[i] = H[1,i,i] + mu
        Vi[i] = V[i,i]
        Vij[i,i] -= V[i,i]

    for idw in prange(dwn):
        nup = np.empty(n,np.float64) # hoisted by numba
        ndw = np.empty(n,np.float64) # hoisted by numba
        sdw = states_dw[idw]
        # Energy contribution
        edw = 0.
        for i in range(n):
            ndw[i] = np.float64((sdw>>i)&uone) 
            edw += edwdiag[i]*ndw[i]
        for iup in range(dup):
            sup = states_up[iup]
            res = edw
            for i in range(n):
                nup[i] = np.float64((sup>>i)&uone)
                res += nup[i]*eupdiag[i]
        # Coulomb contribution
            if hfmode:
                for i in range(n):
                    res += (nup[i]-0.5)*(ndw[i]-0.5)*Vi[i]
                    tmp = 0.
                    for j in range(n):
                        tmp += Vij[i,j]*(nup[j]+ndw[j]-z[j])
                    res += 0.5 * (nup[i]+ndw[i]-z[i]) * tmp
            else:
                for i in range(n):
                    res += nup[i]*ndw[i]*Vi[i]
                    tmp = 0.
                    for j in range(n):
                        tmp += Vij[i,j]*(nup[j]+ndw[j]-z[j])
                    res += 0.5 * (nup[i]+ndw[i]-z[i]) * tmp
            vec_diag[iup+idw*dup] = res


@njit((Array(float64, 3, 'A', readonly=True),
       Array(float64, 2, 'C'),
       Array(uint32, 1, 'C'),
       Array(float64, 1, 'C'),
       Array(float64, 1, 'C'),
       boolean,
       float64),
      parallel=True,cache=True)
def _N_build_ham_local(H, V, states, vec_diag, z, hfmode=False, mu=0.):
    # ___                                   ___                              ___                             
    # \         e  (  n    +  n     )   +   \         U    n     n      +    \        (  n    +  n     ) V    (  n    +  n     )     
    # /__        i     i,up     i,dw        /__        i    i,up  i,dw       /__          i,up    i,dw     ij     j,up    j,dw  
    #     i                                     i                                i!=j                     
    d = states.size
    n = V.shape[0]
    
    eupdiag = np.empty(n,np.float64)
    edwdiag = np.empty(n,np.float64)
    Vi = np.empty(n,np.float64)
    Vij = V.copy()
    for i in range(n):
        eupdiag[i] = H[0,i,i] + mu
        edwdiag[i] = H[1,i,i] + mu
        Vi[i] = V[i,i]
        Vij[i,i] -= V[i,i]

    mask_up = np.uint32((uone<<n)-1) # 0..01..1
    mask_dw = mask_up<<n # 1..10..0
    for idu in prange(d):
        nup = np.empty(n,np.float64) # hoisted by numba
        ndw = np.empty(n,np.float64) # hoisted by numba
        sdu = states[idu]
        sdw = (sdu & mask_dw) >> n
        sup = (sdu & mask_up)
        # Energy contribution
        res = 0.
        for i in range(n):
            ndw[i] = np.float64((sdw>>i)&uone) 
            nup[i] = np.float64((sup>>i)&uone)
            res += edwdiag[i]*(ndw[i]+nup[i])
        # Coulomb contribution
        if hfmode:
            for i in range(n):
                res += (nup[i]-0.5)*(ndw[i]-0.5)*Vi[i]
                tmp = 0.
                for j in range(n):
                    tmp += Vij[i,j]*(nup[j]+ndw[j]-z[j])
                res += 0.5 * (nup[i]+ndw[i]-z[i]) * tmp
        else:
            for i in range(n):
                res += nup[i]*ndw[i]*Vi[i]
                tmp = 0.
                for j in range(n):
                    tmp += Vij[i,j]*(nup[j]+ndw[j]-z[j])
                res += 0.5 * (nup[i]+ndw[i]-z[i]) * tmp
        vec_diag[idu] = res


def build_ham_local(H, V, sct, hfmode=False, mu=0., z=None):
    if z is None:
        if hfmode:
            z = np.ones(H.shape[-1])
        else:
            z = np.zeros(H.shape[-1])
    """Build local Hamiltonian."""
    vec_diag = np.zeros(sct.d)
    if hasattr(sct.states, 'up'):
        _build_ham_local(H, V, sct.states.up, sct.states.dw, vec_diag, z, hfmode, mu)
    else:
        _N_build_ham_local(H, V, sct.states, vec_diag, z, hfmode, mu)
    return vec_diag.view(Local)


class Local(np.ndarray):
    """Local Hamiltonian operator."""
    def matvec(self, other, out=None):
        return np.multiply(self, other, out=out)
    
    def todense(self):
        return np.diag(self)
        