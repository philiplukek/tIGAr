"""
The ``calculusUtils`` module
----------------------------
contains functions and classes to hide the raw UFL involved in referring PDEs
back to the IGA parametric domain.  
"""

# note that these functions simply help prepare a UFL specification of the
# PDE, which is then compiled into efficient code.  These are not being called
# inside some inner loop over quadrature points, and should therefore be
# optimized for generality/readability rather than speed of execution.

from dolfin import *

def getMetric(F):
    """
    Returns a metric tensor corresponding to a given mapping ``F`` from 
    parametric to physical space.
    """
    DF = grad(F)
    return DF.T*DF

def getChristoffel(g):
    """
    Returns Christoffel symbols associated with a metric tensor ``g``.  Indices
    are ordered based on the assumption that the first index is the raised one.
    """
    a,b,c,d = indices(4)
    return as_tensor\
        (0.5*inv(g)[a,b]\
         *(grad(g)[c,b,d]\
           + grad(g)[d,b,c]\
           - grad(g)[d,c,b]), (a,d,c))

def mappedNormal(N,F,normalize=True):
    """
    Returns a deformed normal vector corresponding to the area element with
    normal ``N`` in the parametric reference domain.  Deformation given by
    ``F``.  Optionally, the normal can be left un-normalized by setting
    ``normalize = False``.  In that case, the magnitude is the ratio of 
    deformed to reference area elements.
    """
    DF = grad(F)
    g = getMetric(F)
    n = DF*inv(g)*N
    if(normalize):
        return n/sqrt(inner(n,n))
    else:
        return n
    # sanity check: consistent w/ Nanson formula for invertible DF,
    # metric = (DF)^T * DF

def pinvD(F):
    """
    Returns the Moore--Penrose pseudo-inverse of the derivative of the mapping
    ``F``.
    """
    DF = grad(F)
    g = getMetric(F)
    return inv(g)*DF.T
    
def volumeJacobian(g):
    """
    Returns the volume element associated with the metric ``g``.
    """
    return sqrt(det(g))
    
def surfaceJacobian(g,N):
    """
    Returns the surface element associated with the metric ``g``, for a surface
    oriented in the direction given by unit vector ``N``.
    """
    return sqrt(det(g)*inner(N,inv(g)*N))

# class for tensors in curvilinear coordinates w/ metric g
class CurvilinearTensor:
    """
    Class to represent arbitrary tensors in curvilinear coordinates, with a
    mechanism to distinguish between raised and lowered indices.
    """
    def __init__(self,T,g,lowered=None):
        """
        Create a ``CurvilinearTensor`` with components given by the UFL tensor
        ``T``, on a manifold with metric ``g``.  The sequence of Booleans
        ``lowered`` indicates whether or not each index is lowered.  The 
        default is for all indices to be lowered.
        """
        self.T = T
        self.g = g
        if(lowered != None):
            self.lowered = lowered
        else:
            # default: all lowered indices
            self.lowered = []
            for i in range(0,rank(T)):
                self.lowered += [True,]
                
    def __add__(self,other):
        # TODO: add consistency checks on g and lowered
        return CurvilinearTensor(self.T+other.T,self.g,self.lowered)

    def __sub__(self,other):
        return CurvilinearTensor(self.T-other.T,self.g,self.lowered)

    # for scalar coefficients
    def __rmul__(self,other):
        return CurvilinearTensor(other*self.T,self.g,self.lowered)
                
    # mainly for internal use. not well tested...
    def raiseLowerIndex(self,i):
        """
        Flips the raised/lowered status of the ``i``-th index.
        """
        n = rank(self.T)
        ii = indices(n+1)
        mat = self.g
        if(self.lowered[i]):
            mat = inv(self.g)
        else:
            mat = self.g
        retval = as_tensor(self.T[ii[0:i]+(ii[i],)+ii[i+1:n]]\
                           *mat[ii[i],ii[n]],\
                           ii[0:i]+(ii[n],)+ii[i+1:n])
        return CurvilinearTensor(retval,self.g,\
                                 self.lowered[0:i]\
                                 +[not self.lowered[i],]+self.lowered[i+1:])
    def raiseIndex(self,i):
        """
        Returns an associated tensor with the ``i``-th index raised.
        """
        if(self.lowered[i]):
            return self.raiseLowerIndex(i)
        else:
            return self
        
    def lowerIndex(self,i):
        """
        Returns an associated tensor with the ``i``-th index lowered.
        """
        if(not self.lowered[i]):
            return self.raiseLowerIndex(i)
        else:
            return self

    def sharp(self):
        """
        Returns an associated tensor with all indices raised.
        """
        retval = self
        for i in range(0,rank(self.T)):
            retval = retval.raiseIndex(i)
        return retval

    def flat(self):
        """
        Returns an associated tensor with all indices lowered.
        """
        retval = self
        for i in range(0,rank(self.T)):
            retval = retval.lowerIndex(i)
        return retval

    def rank(self):
        """
        Returns the rank of the tensor.
        """
        return rank(self.T)

def curvilinearInner(T,S):
    """
    Returns the inner product of ``CurvilinearTensor`` objects
    ``T`` and ``S``, inserting factors of the metric and inverse metric
    as needed, depending on the co/contra-variant status of corresponding
    indices.
    """
    Tsharp = T.sharp();
    Sflat = S.flat();
    ii = indices(rank(T.T))
    return as_tensor(Tsharp.T[ii]*Sflat.T[ii],())

# TODO: check/test more thoroughly
def covariantDerivative(T):
    """
    Returns a ``CurvilinearTensor`` that is the covariant derivative of
    the ``CurvilinearTensor`` argument ``T``.
    """
    n = rank(T.T)
    ii = indices(n+2)
    g = T.g
    gamma = getChristoffel(g)
    retval = grad(T.T)
    for i in range(0,n):
        # use ii[n] as the new index of the covariant deriv
        # use ii[n+1] as dummy index
        if(T.lowered[i]):
            retval -= as_tensor(T.T[ii[0:i]+(ii[n+1],)+ii[i+1:n]]\
                                *gamma[(ii[n+1],ii[i],ii[n])],\
                                ii[0:n+1])
        else:
            retval += as_tensor(T.T[ii[0:i]+(ii[n+1],)+ii[i+1:n]]\
                                *gamma[(ii[i],ii[n+1],ii[n])],\
                                ii[0:n+1])
    newLowered = T.lowered+[True,]
    return CurvilinearTensor(retval,g,newLowered)

def curvilinearGrad(T):
    """
    Returns the gradient of ``CurvilinearTensor`` argument ``T``, i.e., the
    covariant derivative with the last index raised.
    """
    n = rank(T.T)
    ii = indices(n+2)
    g = T.g
    deriv = covariantDerivative(T)
    invg = inv(g)
    # raise last index
    retval = as_tensor(deriv.T[ii[0:n+1]]*invg[ii[n:n+2]],\
                       ii[0:n]+(ii[n+1],))
    return CurvilinearTensor(retval,g,T.lowered+[False,])

def curvilinearDiv(T):
    """
    Returns the divergence of the ``CurvilinearTensor`` argument ``T``, i.e.,
    the covariant derivative, but contracting over the new index and the 
    last raised index.  

    NOTE: This operation is invalid for tensors that do not 
    contain at least one raised index.
    """
    n = rank(T.T)
    ii = indices(n)
    g = T.g
    j = -1 # last raised index
    for i in range(0,n):
        if(not T.lowered[i]):
            j = i
    if(j == -1):
        print("ERROR: Divergence operator requires at least one raised index.")
        exit()
    deriv = covariantDerivative(T)
    retval = as_tensor(deriv.T[ii[0:n]+(ii[j],)],ii[0:j]+ii[j+1:n])
    return CurvilinearTensor(retval,g,T.lowered[0:j]+T.lowered[j+1:n])

# Cartesian differential operators in deformed configuration
# N.b. that, when applied to tensor-valued f, f is considered to be
# in the Cartesian coordinates of the physical configuration, NOT in the
# local coordinate chart w.r.t. which derivatives are taken by FEniCS
def cartesianGrad(f,F):
    n = rank(f)
    ii = indices(n+2)
    pinvDF = pinvD(F)
    return as_tensor(grad(f)[ii[0:n+1]]\
                     *pinvDF[ii[n],ii[n+1]],\
                     ii[0:n]+(ii[n+1],))
def cartesianDiv(f,F):
    n = rank(f)
    ii = indices(n)
    return as_tensor(cartesianGrad(f,F)[ii+(ii[n-1],)],ii[0:n-1])

# only applies to f w/ rank 1, in 3D
def cartesianCurl(f,F):
    eps = PermutationSymbol(3)
    gradf = cartesianGrad(f,F)
    (i,j,k) = indices(3)
    return as_tensor(eps[i,j,k]*gradf[k,j],(i,))

# pushforwards for compatible spaces; output is in cartesian coordinates for
# physical space

# curl-conserving
def cartesianPushforwardN(u,F):
    DF = grad(F)
    return inv(DF.T)*u

# div-conserving
def cartesianPushforwardRT(v,F):
    DF = grad(F)
    return DF*v/det(DF)

# mass-conserving
def cartesianPushforwardW(phi,F):
    DF = grad(F)
    return phi/det(DF)

# TODO: rename this to ScaledMeasure
# I can't just scale a measure by a Jacobian, so I'll store them separately,
# then overload __rmul__()
class tIGArMeasure:

    # if quadDeg==None, then this works if meas is a FEniCS measure, OR if
    # meas is another tIGAr measure; it's a good idea to set quadDeg
    # if meas is a FEniCS measure, though, since the convoluted expressions
    # for rational splines tend to drive up the automatically-determined
    # quadrature degree
    def __init__(self,J,meas,quadDeg=None,boundaryMarkers=None):
        if(quadDeg != None):
            # TODO: is this reflected in the calling scope?
            meas = meas(metadata={'quadrature_degree': quadDeg})
        if(boundaryMarkers != None):
            meas = meas(subdomain_data=boundaryMarkers)
        self.meas = meas
        self.J = J

    # pass an argument indicating a subdomain marker
    def __call__(self,marker):
        return tIGArMeasure(self.J,self.meas(marker))
        
    def __rmul__(self, other):
        return (other*self.J)*self.meas

def getQuadRule(n):
    """
    Return a list of points and a list of weights for integration over the
    interval (-1,1), using ``n`` quadrature points.  

    NOTE: This functionality is mainly intended
    for use in through-thickness integration of Kirchhoff--Love shell
    formulations, but might also be useful for implementing space--time
    formulations using a mixed element to combine DoFs from various time
    levels.
    """
    if(n==1):
        xi = [Constant(0.0),]
        w = [Constant(2.0),]
        return (xi,w)
    if(n==2):
        xi = [Constant(-0.5773502691896257645091488),
              Constant(0.5773502691896257645091488)]
        w = [Constant(1.0),
             Constant(1.0)]
        return (xi,w)
    if(n==3):
        xi = [Constant(-0.77459666924148337703585308),
              Constant(0.0),
              Constant(0.77459666924148337703585308)]
        w = [Constant(0.55555555555555555555555556),
             Constant(0.88888888888888888888888889),
             Constant(0.55555555555555555555555556)]
        return (xi,w)
    if(n==4):
        xi = [Constant(-0.86113631159405257524),
              Constant(-0.33998104358485626481),
              Constant(0.33998104358485626481),
              Constant(0.86113631159405257524)]
        w = [Constant(0.34785484513745385736),
             Constant(0.65214515486254614264),
             Constant(0.65214515486254614264),
             Constant(0.34785484513745385736)]
    
    #TODO add more quadrature rules
    
    if(mpirank==0):
        print("ERROR: invalid number of quadrature points requested.")
        exit()

def getQuadRuleInterval(n,L):
    """
    Returns an ``n``-point quadrature rule for the interval 
    (-``L``/2,``L``/2), consisting of a list of points and list of weights.
    """
    xi_hat, w_hat = getQuadRule(n)
    xi = []
    w = []
    for i in range(0,n):
        xi += [L*xi_hat[i]/2.0,]
        w += [L*w_hat[i]/2.0,]
    return (xi,w)
