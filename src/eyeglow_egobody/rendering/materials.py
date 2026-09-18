"""Live sphere geometry for participant-colored eyeballs."""
from vtkmodules.vtkFiltersCore import vtkGlyph3D
from vtkmodules.vtkFiltersSources import vtkSphereSource


def eye_sphere_source(radius):
    sphere = vtkSphereSource()
    sphere.SetRadius(radius)
    sphere.SetThetaResolution(32)
    sphere.SetPhiResolution(24)
    return sphere


def eye_spheres(centers, sphere):
    glyphs = vtkGlyph3D()
    glyphs.SetInputData(centers)
    glyphs.SetSourceConnection(sphere.GetOutputPort())
    glyphs.ScalingOff()
    glyphs.OrientOff()
    return glyphs

