import pandas as pd
import numpy as np
import time

def measure_generation_times(n_samples: int = 1000):
    timings = {}

    # Normal distribution
    start = time.time()
    _ = np.random.normal(loc=0, scale=1, size=n_samples)
    timings['normal'] = time.time() - start

    # Gamma distribution
    start = time.time()
    _ = np.random.gamma(shape=0.30, scale=1/3000000, size=n_samples)
    timings['gamma'] = time.time() - start

    # Exponential distribution
    start = time.time()
    _ = np.random.exponential(scale=1.0, size=n_samples)
    timings['exponential'] = time.time() - start

    # Pareto distribution
    start = time.time()
    _ = np.random.pareto(a=3.0, size=n_samples)
    timings['pareto'] = time.time() - start

    # Create DataFrame
    df = pd.DataFrame(list(timings.items()), columns=['Distribution', 'Generation Time (s)'])
    return df

# Example usage
if __name__ == "__main__":
    result = measure_generation_times(10 * 1000 * 1000)
    print(result)
