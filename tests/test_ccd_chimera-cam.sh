#!/bin/bash
set -xe
chimera-cam --config ../etc/chimera_ccd.config -v --version
chimera-cam --config ../etc/chimera_ccd.config -v --expose -n 2 -t 2 -i 3 -o './$DATE-$TIME.fits' -f Rc1528 --shutter=open
chimera-cam --config ../etc/chimera_ccd.config -v --expose --shutter=close --object=Test
chimera-cam --config ../etc/chimera_ccd.config -v --expose --shutter=leave --binning=BINNING 2x2 
chimera-cam --config ../etc/chimera_ccd.config -v --expose --compress=gzip
chimera-cam --config ../etc/chimera_ccd.config -v --expose --compress=zip
chimera-cam --config ../etc/chimera_ccd.config -v --expose --compress=bz2
chimera-cam --config ../etc/chimera_ccd.config -v --expose --compress=fits_rice --ignore-dome
# chimera-cam --config ../etc/chimera_ccd.config -v --expose --force-display
# chimera-cam --config ../etc/chimera_ccd.config -v -T -1 
# chimera-cam --config ../etc/chimera_ccd.config -v --start-fan
# chimera-cam --config ../etc/chimera_ccd.config -v --stop-cooling
# chimera-cam --config ../etc/chimera_ccd.config -v --stop-fan
# chimera-cam --config ../etc/chimera_ccd.config -v -F
# chimera-cam --config ../etc/chimera_ccd.config -v --info
# chimera-cam --config ../etc/chimera_ccd.config -v --expose --bias
# chimera-cam --config ../etc/chimera_ccd.config -v --expose --flat
# chimera-cam --config ../etc/chimera_ccd.config -v --expose --sky-flat
# chimera-cam --config ../etc/chimera_ccd.config -v --expose --dark -t2

# # open dome slit, slew telescope, take an exposure
# chimera-dome --open-slit --track && \
# chimera-tel --slew --az 10 --alt 60 && \
# chimera-cam --config ../etc/chimera_ccd.config -v -w --expose 
