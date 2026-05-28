"""Export findings (measurement report).

The `report` module serialises a measurement to disk:
  - results.json  Sa/Sq/Sz/Ssk/Sku + processing time + provenance.
  - height.png    8-bit grayscale render of the height map for quick viewing.
  - roughness.png 8-bit grayscale render of the roughness residual.
"""

from microprojection.export.report import save_report

__all__ = ["save_report"]
