import numpy as np
from astropy.io import fits


def concatenate_quad_arrays(
    array_4, array_3, array_2, array_1, header=None, trim_data=False
):
    """
    Concatenate four 2D arrays into a single 2x2 grid.

    Layout:
    array_4  array_3
    array_1  array_2
    """
    if header and trim_data:
        datasec = header["DATASEC"][1:-1]  # Remove brackets
        datasec = [int(j) for i in datasec.split(",") for j in i.split(":")]
        datasec = [
            datasec[2] - 1,
            datasec[3],
            datasec[0] - 1,
            datasec[1],
        ]  # Convert to numpy 0-based indexing
    else:
        datasec = [0, array_1.shape[0], 0, array_1.shape[1]]

    ixsize, iysize = datasec[1] - datasec[0], datasec[3] - datasec[2]
    oxsize, oysize = ixsize * 2, iysize * 2

    outimage = np.zeros((oxsize, oysize), dtype=array_4.dtype)

    # Top left
    outimage[0:ixsize, 0:iysize] = array_4[
        datasec[0] : datasec[1], datasec[2] : datasec[3]
    ]
    # Top right
    outimage[0:ixsize, iysize:oysize] = array_3[
        datasec[0] : datasec[1], datasec[2] : datasec[3]
    ][:, ::-1]
    # Bottom left
    outimage[ixsize:oxsize, 0:iysize] = array_1[
        datasec[0] : datasec[1], datasec[2] : datasec[3]
    ][::-1]
    # Bottom right
    outimage[ixsize:oxsize, iysize:oysize] = array_2[
        datasec[0] : datasec[1], datasec[2] : datasec[3]
    ][::-1, ::-1]

    # Rotate by 90 degrees to have North up, East left
    outimage = np.rot90(outimage)

    return outimage
