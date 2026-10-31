import sys,unittest,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from strikezone.ball.size_forecast import forecast,predict,forecast_updates

def sample(f):
    t=f/30;q=.05+.1*t
    return dict(frame=f,diameter_px=1/q,center_xy=[(20+5*t)/q,(10+2*t+3*t*t)/q])

class ForecastTests(unittest.TestCase):
    def test_updates_are_causal_and_include_new_observations(self):
        rows=[sample(i) for i in range(12)]
        updates=forecast_updates(rows,50)
        self.assertEqual(updates[:7],forecast_updates(rows[:7],50))
        self.assertEqual(updates[-1]['training_frames'],list(range(12)))
        changed=[dict(r) for r in rows];changed[-1]['diameter_px']*=1.2
        newer=forecast_updates(changed,50)
        self.assertEqual(updates[:-1],newer[:-1])
        self.assertNotEqual(updates[-1]['inverse_diameter_coefficients'],newer[-1]['inverse_diameter_coefficients'])

    def test_past_crossing_remains_estimate(self):
        updates=forecast_updates([sample(i) for i in range(40)],50)
        self.assertEqual(updates[-1]['candidate']['temporal_relation'],'past_estimate')
        self.assertAlmostEqual(updates[-1]['candidate']['frame'],updates[4]['candidate']['frame'])

    def test_updates_ignore_duplicate_and_invalid_detections(self):
        rows=[sample(i) for i in range(6)]
        rows.extend([sample(2),dict(frame=7,diameter_px=None),dict(sample(8),repeated=True)])
        updates=forecast_updates(rows,50)
        self.assertEqual(len(updates),6)
        self.assertIn('provisional_fewer_than_five_observations',updates[2]['flags'])

    def test_recovers_projection_and_target(self):
        m=forecast([sample(i) for i in range(5)],50)
        p=predict(m,12);truth=sample(12)
        self.assertAlmostEqual(p['diameter_px'],truth['diameter_px'])
        self.assertAlmostEqual(p['center_xy'][1],truth['center_xy'][1])
        self.assertAlmostEqual(predict(m,m['candidate']['frame'])['diameter_px'],50*9.125/math.pi/17)
    def test_future_does_not_leak_into_fit(self):
        rows=[sample(i) for i in range(10)];first=forecast(rows,50)
        for r in rows[5:]:r['diameter_px']=100;r['center_xy']=[9999,9999]
        self.assertEqual(first,forecast(rows,50))
    def test_duplicates_and_missing_not_counted(self):
        rows=[sample(i) for i in range(5)];rows[2]['repeated']=True
        self.assertEqual(forecast(rows,50)['status'],'insufficient_observations')
    def test_growing_ball_no_future_crossing(self):
        rows=[dict(frame=i,diameter_px=5+i,center_xy=[i,i]) for i in range(5)]
        self.assertEqual(forecast(rows,50)['status'],'not_shrinking')

if __name__=='__main__':unittest.main()
