"""Reproduce constant-column IF blindness on synthetic data only."""
import json
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from ml import campaign as C
from ml.features import select_features, envelope_exceedance_counts


def experiment():
    rng = np.random.default_rng(0)
    variables = rng.normal(size=(464,2))
    test = np.array([[0.,0.,loss] for loss in (0.,1.,53.,1e6)])
    result = {'data': 'synthetic only; no campaign detector fitted',
              'sklearn_version': sklearn.__version__, 'numpy_version': np.__version__,
              'n_train': 464, 'n_estimators':200, 'seed':0,
              'test_loss_values':test[:,2].tolist()}
    for name, last in [('constant',np.zeros(464)),('synthetic_noise_control',rng.normal(0,.001,464))]:
        train = np.column_stack([variables,last])
        model = IsolationForest(n_estimators=200, max_samples=256,
                                contamination='auto', random_state=0).fit(train)
        used = sum(2 in set(tree.tree_.feature[tree.tree_.feature >= 0]) for tree in model.estimators_)
        result[name] = {'scores':model.score_samples(test).tolist(),
                        'predictions':model.predict(test).tolist(),
                        'trees_splitting_last_column':used,
                        'train_sha256':C.sha256_bytes(train.tobytes())}
    df = pd.DataFrame({'link-synthetic.traffic.lossPct':np.zeros(464)})
    envelope = select_features(df)['envelope']
    result['envelope_test'] = envelope_exceedance_counts(
        pd.DataFrame({'link-synthetic.traffic.lossPct':test[:,2]}),envelope).to_dict('list')
    result['constant_score_invariant'] = len(set(result['constant']['scores'])) == 1
    result['constant_never_split'] = result['constant']['trees_splitting_last_column'] == 0
    return result


if __name__ == '__main__':
    result = experiment()
    C.atomic_json(C.ROOT/'results/report/if_constant_blindness.json',result)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['constant_score_invariant'] and result['constant_never_split'] else 1)
