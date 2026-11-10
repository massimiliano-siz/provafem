#!/bin/bash
# Matrice materiale x spessore, disco su guarnizione EPDM 2 mm; uscite a 0.2, 0.5 e 2 bar.
cd "$(dirname "$0")"
run() {  # nome  t  E  nu
  local name=$1 t=$2 E=$3 nu=$4
  local h=$(python3 -c "print(min(4.5, $t/4))")
  python3 build_model.py "{\"t\":$t,\"Rseal\":200.0,\"p\":0.2,\"Kg\":3.3,\"E\":$E,\"nu\":$nu,\"h_glob\":$h,\"out\":\"$name\"}" > /dev/null 2>&1
  sed -i 's/^0.3333333,0.6666667,1.0$/0.1,0.25,1.0/' $name.inp
  OMP_NUM_THREADS=2 ccx -i $name > $name.log 2>&1
  echo "$(date +%T) $name finito: $(grep -c 'Job finished' $name.log) $(tail -1 $name.sta)"
}
export -f run
cat > jobs.txt <<J
hdpe25 25 1000 0.40
pmma25 25 3000 0.37
hdpe20 20 1000 0.40
pmma20 20 3000 0.37
hdpe15 15 1000 0.40
pmma15 15 3000 0.37
hdpe10 10 1000 0.40
pmma10 10 3000 0.37
J
xargs -P 2 -L 1 bash -c 'run "$@"' _ < jobs.txt
echo TUTTI_FINITI
