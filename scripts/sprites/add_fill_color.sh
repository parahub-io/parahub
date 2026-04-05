#!/bin/bash
# Add fill color to SVG path elements

svg_file=$1
color=$2

# Add fill="color" to all <path> tags that don't have fill attribute
sed -i "s/<path /<path fill=\"${color}\" /g" "$svg_file"

echo "Added fill $color to $svg_file"
