pub trait FloatExt: Sized {
    const EPS: Self;

    /// `self == other`
    fn eq(self, other: Self) -> bool {
        self.almost_eq(other, Self::EPS)
    }

    /// `self ~= other` (within `acceptable_difference`)
    fn almost_eq(self, other: Self, acceptable_difference: Self) -> bool;

    /// `self != other`
    fn not_eq(self, other: Self) -> bool;

    /// Performs a linear interpolation between two values based on the given weight.
    fn lerp(value1: Self, value2: Self, amount: Self) -> Self;
}

macro_rules! impl_float_ext {
    ( $ty:ty ) => {
        impl FloatExt for $ty {
            const EPS: Self = <$ty>::EPSILON;

            fn almost_eq(self, other: Self, acceptable_difference: Self) -> bool {
                Self::abs(self - other) <= acceptable_difference
            }

            fn not_eq(self, other: Self) -> bool {
                Self::abs(self - other) >= Self::EPS
            }

            // .NET 10 Double.Lerp uses MultiplyAddEstimate for the first product and sum.
            fn lerp(value1: Self, value2: Self, amount: Self) -> Self {
                #[cfg(any(target_arch = "x86", target_arch = "x86_64"))]
                let fused = std::is_x86_feature_detected!("fma");
                #[cfg(target_arch = "aarch64")]
                let fused = true;
                #[cfg(not(any(
                    target_arch = "x86",
                    target_arch = "x86_64",
                    target_arch = "aarch64"
                )))]
                let fused = false;

                if fused {
                    Self::mul_add(value1, 1.0 - amount, value2 * amount)
                } else {
                    value1 * (1.0 - amount) + value2 * amount
                }
            }
        }
    };
}

impl_float_ext!(f32);
impl_float_ext!(f64);
