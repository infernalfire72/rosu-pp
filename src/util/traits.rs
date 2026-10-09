/// Mimics the C# `IEnumerable<T>` interface.
pub trait IEnumerable<T>: Sized {
    fn cs_where<F: FnMut(&T) -> bool>(self, f: F) -> Self;

    fn cs_add_in_place(&mut self, item: T) -> usize
    where
        T: Ord;
}

/// Mimics the C# `IOrderedEnumerable<T>` interface.
pub trait IOrderedEnumerable<T>: IEnumerable<T> {
    /// Sorts the elements of a sequence in descending order.
    ///
    /// This method performs a stable sort; that is, if the keys of two elements
    /// are equal, the order of the elements is preserved. In contrast, an unstable sort does not
    /// preserve the order of elements that have the same key.
    ///
    /// <https://learn.microsoft.com/en-us/dotnet/api/system.linq.enumerable.orderbydescending>
    fn cs_order_descending(self) -> Self;
}

impl<T> IEnumerable<T> for Vec<T> {
    /// Filters a sequence of values based on a predicate.
    ///
    /// <https://learn.microsoft.com/en-us/dotnet/api/system.linq.enumerable.where>
    fn cs_where<F: FnMut(&T) -> bool>(mut self, f: F) -> Self {
        self.retain(f);

        self
    }

    /// Adds the given item to the list according to standard sorting rules. Do not use on unsorted lists.
    ///
    /// <https://github.com/ppy/osu-framework/blob/master/osu.Framework/Extensions/ExtensionMethods.cs#L34>
    fn cs_add_in_place(&mut self, item: T) -> usize
    where
        T: Ord,
    {
        // List<T>.BinarySearch returns the first equal midpoint it visits.
        // Rust's binary_search chooses a different position among equal values,
        // which changes the ordering of equal strain peaks with different lengths.
        let mut low = 0;
        let mut high = self.len();
        let index = loop {
            if low == high {
                break low;
            }

            let mid = low + (high - low - 1) / 2;

            match self[mid].cmp(&item) {
                std::cmp::Ordering::Less => low = mid + 1,
                std::cmp::Ordering::Equal => break mid,
                std::cmp::Ordering::Greater => high = mid,
            }
        };
        self.insert(index, item);
        index
    }
}

impl IOrderedEnumerable<f64> for Vec<f64> {
    fn cs_order_descending(mut self) -> Self {
        self.sort_by(|a, b| b.total_cmp(a));

        self
    }
}
