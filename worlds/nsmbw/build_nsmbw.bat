:: CALL ./worlds/nsmbw/build_poptracker.bat
cd ./worlds/nsmbw/NSMBW_client/riivolution_patch/Kamek-Ninja-Template
CALL ./config_and_build.bat
cd ../../../../..
py -3.13 -m worlds.nsmbw.dev_files.build_tracker
py -3.13 ./launcher.py "Build APWorlds" "NSMBW"