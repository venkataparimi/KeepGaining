"""Test fastest CSV generation approaches."""
import numpy as np
from io import StringIO
import time

n = 362000
n_cols = 60

# Generate test data
print(f"Generating {n} rows x {n_cols} cols...")
data = np.random.rand(n, n_cols)
data[np.random.rand(n, n_cols) < 0.05] = np.nan  # 5% NaN

# Approach 1: List comprehension with indexing
def approach_1():
    # Convert each column to string list
    str_cols = []
    for j in range(n_cols):
        col = data[:, j]
        nan_mask = np.isnan(col)
        str_arr = col.astype(str)
        str_arr[nan_mask] = '\\N'
        str_cols.append(str_arr.tolist())
    
    # Build CSV
    lines = []
    for i in range(n):
        line = '\t'.join(str_cols[j][i] for j in range(n_cols))
        lines.append(line)
    return '\n'.join(lines)

# Approach 2: Build with transposed iteration
def approach_2():
    # Convert each column to string list
    str_cols = []
    for j in range(n_cols):
        col = data[:, j]
        nan_mask = np.isnan(col)
        str_arr = col.astype(str)
        str_arr[nan_mask] = '\\N'
        str_cols.append(str_arr.tolist())
    
    # Use zip on pre-converted lists
    return '\n'.join(
        '\t'.join(row) for row in zip(*str_cols)
    )

# Approach 3: numpy savetxt to StringIO
def approach_3():
    buf = StringIO()
    # Replace NaN with a placeholder number, then fix in string
    data_copy = np.nan_to_num(data, nan=-999999.999999)
    np.savetxt(buf, data_copy, delimiter='\t', fmt='%.6f')
    result = buf.getvalue()
    return result.replace('-999999.999999', '\\N')

# Approach 4: Build numpy string array row by row
def approach_4():
    # Build string array directly
    nan_mask = np.isnan(data)
    str_data = data.astype(str)
    str_data[nan_mask] = '\\N'
    
    # Join columns with tab for each row
    lines = ['\t'.join(row) for row in str_data]
    return '\n'.join(lines)

# Approach 5: Vectorized char array
def approach_5():
    nan_mask = np.isnan(data)
    str_data = data.astype('U32')  # Unicode strings up to 32 chars
    str_data[nan_mask] = '\\N'
    
    # Use numpy char module to join
    tab = np.array('\t')
    rows = np.apply_along_axis(lambda x: tab.join(x), 1, str_data)
    newline = '\n'
    return newline.join(rows.tolist())

print("\nTesting approaches...")

t1 = time.time()
result1 = approach_1()
t2 = time.time()
print(f"Approach 1 (index loop): {t2-t1:.2f}s")

t1 = time.time()
result2 = approach_2()
t2 = time.time()
print(f"Approach 2 (zip on lists): {t2-t1:.2f}s")

t1 = time.time()
result3 = approach_3()
t2 = time.time()
print(f"Approach 3 (np.savetxt): {t2-t1:.2f}s")

t1 = time.time()
result4 = approach_4()
t2 = time.time()
print(f"Approach 4 (str array + list comp): {t2-t1:.2f}s")

t1 = time.time()
result5 = approach_5()
t2 = time.time()
print(f"Approach 5 (vectorized char): {t2-t1:.2f}s")

# Verify results match (first 1000 chars)
print(f"\nResult 1 len: {len(result1)}")
print(f"Result 2 len: {len(result2)}")
